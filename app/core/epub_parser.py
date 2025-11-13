# -*- coding: utf-8 -*-
"""
EPUB 파일의 내부 구조를 분석하고, 목차 및 콘텐츠 정보를 추출하는 핵심 파서 모듈입니다.
이 모듈은 디스크 I/O 없이 메모리 내 바이트 스트림을 직접 처리하도록 설계되었습니다.
"""
import io
import zipfile
import posixpath
import re
import urllib.parse
import logging
from typing import Any, Dict, List
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
from lxml import etree
import warnings
from app.domain.models import TocItem

# BeautifulSoup이 XHTML을 HTML 파서로 처리할 때 발생하는 경고를 무시합니다.
# EPUB 내 XHTML은 XML에 가깝지만, HTML 파서로도 대부분 안정적으로 처리 가능합니다.
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

logger = logging.getLogger(__name__)

class EpubParser:
    """
    EPUB 컨테이너(ZIP)를 파싱하여 목차, 파일 목록, 텍스트 콘텐츠 등을 추출하는 유틸리티 클래스입니다.
    EPUB 2와 EPUB 3 표준의 주요 차이점(특히 목차 파일)을 모두 처리할 수 있습니다.
    """
    # 본문이 아닐 가능성이 높은 파일을 식별하기 위한 키워드 (정규표현식, 대소문자 무시)
    DEFAULT_EXCLUDE_PATTERNS = tuple(re.compile(p, re.I) for p in ("cover", "toc", "copyright", "nav"))

    def _normalize_zip_path(self, path: str) -> str:
        """
        ZIP 압축 파일 내의 경로를 표준 형식으로 변환합니다.
        - URL 인코딩(예: '%20')을 일반 문자로 디코딩합니다.
        - 윈도우 스타일의 역슬래시('\\')를 슬래시('/')로 통일합니다.
        - './' 또는 '../' 같은 상대 경로를 정리합니다.

        Args:
            path (str): 정규화할 원본 경로 문자열.

        Returns:
            str: 표준 형식으로 변환된 경로 문자열.
        """
        if not path: return path
        # URL 디코딩 및 경로 구분자 통일
        normalized_path = urllib.parse.unquote(path).replace("\\", "/")
        # 상대 경로 해석 (예: 'OEBPS/../Text/chapter1.xhtml' -> 'Text/chapter1.xhtml')
        return posixpath.normpath(normalized_path)

    def _resolve_href(self, base_dir: str, href: str) -> str:
        """
        베이스 디렉토리와 href(앵커 포함 가능)를 조합하여 정규화된 전체 경로를 생성합니다.
        앵커(#fragment)는 경로 정규화 과정에서 보존됩니다.
        """
        if not href:
            return self._normalize_zip_path(base_dir)

        path_part, fragment = href, ""
        if "#" in path_part:
            path_part, fragment = path_part.split("#", 1)
            fragment = "#" + fragment

        # href가 비어있는 경우(e.g., href="#some_id")를 처리
        if path_part:
            full_path = self._normalize_zip_path(posixpath.join(base_dir, path_part))
        else:
            full_path = self._normalize_zip_path(base_dir)
        
        return full_path + fragment

    def _zip_read(self, zf: zipfile.ZipFile, path: str) -> bytes:
        """
        ZipFile 객체에서 정규화된 경로의 파일을 안전하게 읽어 바이트를 반환합니다.
        경로가 정확히 일치하지 않을 경우를 대비해, 정규화된 경로명으로 다시 한번 탐색합니다.

        Args:
            zf (zipfile.ZipFile): 열려 있는 ZipFile 객체.
            path (str): 읽고자 하는 파일의 ZIP 내 경로.

        Returns:
            bytes: 파일의 내용 (바이트).

        Raises:
            KeyError: ZIP 파일 내에서 해당 경로의 파일을 찾지 못한 경우.
        """
        normalized_path = self._normalize_zip_path(path)
        try:
            return zf.read(normalized_path)
        except KeyError:
            # OPF 파일 등에서 경로가 비표준적으로 기록된 경우를 위한 폴백(fallback) 로직
            for zip_info in zf.infolist():
                if self._normalize_zip_path(zip_info.filename) == normalized_path:
                    return zf.read(zip_info.filename)
            logger.error(f"ZIP에서 파일을 찾을 수 없습니다: {path} (정규화된 경로: {normalized_path})")
            raise

    def _find_opf_path(self, zf: zipfile.ZipFile) -> str:
        """
        EPUB 표준에 따라 'META-INF/container.xml'을 파싱하여
        EPUB의 핵심 메타데이터 파일(.opf)의 전체 경로를 찾습니다.

        Args:
            zf (zipfile.ZipFile): EPUB 파일의 ZipFile 객체.

        Returns:
            str: .opf 파일의 ZIP 내 전체 경로.
        """
        try:
            container_xml = self._zip_read(zf, "META-INF/container.xml")
        except KeyError:
            raise FileNotFoundError("EPUB의 필수 파일 'META-INF/container.xml'을 찾을 수 없습니다.")
        
        root = etree.fromstring(container_xml)
        # XML 네임스페이스를 사용하여 'rootfile' 요소를 정확히 찾습니다.
        ns = {"c": "urn:oasis:names:tc:opendocument:xmlns:container"}
        opf_path = root.xpath("string(.//c:rootfile/@full-path)", namespaces=ns)
        
        if not opf_path:
            raise ValueError("container.xml에서 .opf 파일 경로('full-path')를 찾을 수 없습니다.")
        return self._normalize_zip_path(opf_path)

    def _parse_opf_bytes(self, opf_bytes: bytes) -> (Dict[str, Dict[str, str]], Dict[str, Any]):
        """
        .opf 파일의 바이트 데이터를 파싱하여 'manifest'와 'spine' 정보를 추출합니다.

        - manifest: EPUB을 구성하는 모든 파일(xhtml, css, 이미지 등)의 목록과 속성.
        - spine: 책의 콘텐츠가 실제로 읽히는 순서.

        Args:
            opf_bytes (bytes): .opf 파일의 전체 바이트 데이터.

        Returns:
            tuple: (manifest 딕셔너리, (spine ID 리스트, spine 속성 딕셔너리))
        """
        root = etree.fromstring(opf_bytes)
        # .opf 파일의 네임스페이스는 버전에 따라 다를 수 있으므로 동적으로 가져옵니다.
        ns = {"opf": root.nsmap.get(None) or "http://www.idpf.org/2007/opf"}
        
        # manifest: 각 item의 id를 키로 하는 딕셔너리 생성
        manifest_map = {
            item.get("id"): {
                "href": item.get("href"), 
                "media-type": item.get("media-type"),
                "properties": item.get("properties", "") # EPUB 3에서 사용
            }
            for item in root.xpath(".//opf:manifest/opf:item", namespaces=ns)
            if item.get("id") and item.get("href")
        }
        
        # spine: itemref의 idref 순서대로 리스트 생성
        spine_elem = root.find(".//opf:spine", namespaces=ns)
        spine_ids = [item.get("idref") for item in spine_elem.xpath("opf:itemref", namespaces=ns)]
        # EPUB 2 목차(.ncx)를 찾기 위한 'toc' 속성
        spine_props = {"toc": spine_elem.get("toc")}
        
        return manifest_map, (spine_ids, spine_props)

    def get_text_files_from_spine(self, opf_path: str, manifest: Dict, spine_ids: List[str]) -> List[str]:
        """
        읽기 순서(spine)에 정의된 파일들 중, 실제 본문에 해당하는 텍스트 파일들의
        전체 경로 목록을 반환합니다.

        Args:
            opf_path (str): .opf 파일의 경로 (상대 경로 계산 기준).
            manifest (Dict): _parse_opf_bytes에서 추출한 manifest 정보.
            spine_ids (List[str]): _parse_opf_bytes에서 추출한 spine의 ID 순서.

        Returns:
            List[str]: 본문 텍스트 파일들의 ZIP 내 전체 경로 리스트.
        """
        opf_dir = posixpath.dirname(opf_path)
        text_files = []
        for idref in spine_ids:
            item = manifest.get(idref)
            if not item or not item.get("href"): continue
            
            href = item.get("href")
            # 제외 키워드(cover, toc 등)에 해당하지 않는 파일만 필터링
            if not any(p.search(href) for p in self.DEFAULT_EXCLUDE_PATTERNS):
                # .opf 파일 기준 상대 경로를 ZIP 루트 기준 전체 경로로 변환
                full_path = self._normalize_zip_path(posixpath.join(opf_dir, href))
                text_files.append(full_path)
        return text_files

    def get_plain_text(self, content: bytes) -> str:
        """
        HTML/XHTML 바이트에서 스크립트, 스타일 태그를 제거하고 순수 텍스트만 추출합니다.

        Args:
            content (bytes): HTML/XHTML 파일의 바이트 데이터.

        Returns:
            str: 추출된 순수 텍스트.
        """
        try:
            # lxml 파서가 더 빠르고 안정적입니다.
            soup = BeautifulSoup(content, "lxml")
        except Exception:
            # lxml이 설치되지 않은 경우를 대비한 폴백
            soup = BeautifulSoup(content, "html.parser")
        
        # 텍스트가 아닌 콘텐츠(스크립트, 스타일) 제거
        for tag in soup(["script", "style"]):
            tag.decompose()
        
        return soup.get_text(separator=" ", strip=True)

    def _flatten_toc(self, toc_tree: List[Dict[str, Any]]) -> List[TocItem]:
        """재귀적으로 구성된 목차 트리 구조를 평탄한 리스트(DTO)로 변환합니다."""
        flat_list = []
        for item in toc_tree:
            # 'children' 키를 제외하고 TocItem DTO 객체 생성
            flat_list.append(TocItem(title=item['title'], href=item['href'], level=item['depth']))
            # 자식 노드가 있으면 재귀적으로 호출하여 리스트에 추가
            if item.get('children'):
                flat_list.extend(self._flatten_toc(item['children']))
        return flat_list

    def get_toc_from_stream(self, zf: zipfile.ZipFile, opf_path: str, manifest: Dict, spine_props: Dict) -> List[TocItem]:
        """
        EPUB 스트림에서 목차(TOC)를 추출합니다.

        **EPUB 2/3 호환성 처리:**
        1.  **EPUB 3 시도**: `manifest`에서 `properties="nav"` 속성을 가진 항목(nav.xhtml)을 찾아 파싱합니다.
        2.  **EPUB 2 폴백**: EPUB 3 방식이 실패하면, `spine`의 `toc` 속성이 가리키는 `.ncx` 파일을 찾아 파싱합니다.

        Args:
            zf (zipfile.ZipFile): EPUB의 ZipFile 객체.
            opf_path (str): .opf 파일의 경로.
            manifest (Dict): manifest 정보.
            spine_props (Dict): spine의 속성 정보.

        Returns:
            List[TocItem]: 평탄화된 목차 항목 DTO 리스트.
        """
        opf_dir = posixpath.dirname(opf_path)
        
        # --- 1. EPUB 3 방식 (nav.xhtml) ---
        nav_item = next((item for item in manifest.values() if 'nav' in item.get('properties', '')), None)
        if nav_item:
            try:
                nav_path = self._normalize_zip_path(posixpath.join(opf_dir, nav_item['href']))
                nav_content = self._zip_read(zf, nav_path)
                toc_tree = self._parse_toc_nav_xhtml(nav_content, nav_path)
                if toc_tree:
                    logger.info("EPUB 3 네비게이션 문서(nav.xhtml)에서 목차를 성공적으로 추출했습니다.")
                    return self._flatten_toc(toc_tree)
            except Exception as e:
                logger.warning(f"EPUB 3 목차 분석 중 오류 발생 (EPUB 2로 폴백 시도): {e}")

        # --- 2. EPUB 2 방식 (.ncx) ---
        ncx_id = spine_props.get('toc')
        ncx_item = manifest.get(ncx_id) if ncx_id else None
        # 'toc' 속성이 없는 비표준 파일을 위해 media-type으로도 탐색
        if not ncx_item:
            ncx_item = next((item for item in manifest.values() if item.get('media-type') == 'application/x-dtbncx+xml'), None)

        if ncx_item:
            try:
                ncx_path = self._normalize_zip_path(posixpath.join(opf_dir, ncx_item['href']))
                ncx_content = self._zip_read(zf, ncx_path)
                toc_tree = self._parse_toc_ncx(ncx_content, ncx_path)
                if toc_tree:
                    logger.info("EPUB 2 목차 파일(.ncx)에서 목차를 성공적으로 추출했습니다.")
                    return self._flatten_toc(toc_tree)
            except Exception as e:
                logger.error(f"EPUB 2 목차 분석 중 오류 발생: {e}")
        
        logger.warning("EPUB에서 유효한 목차를 찾지 못했습니다.")
        return []

    def _parse_toc_nav_xhtml(self, data: bytes, nav_full_path: str) -> List[Dict[str, Any]]:
        """EPUB 3의 nav.xhtml 파일을 파싱하여 목차 트리 구조를 생성합니다."""
        soup = BeautifulSoup(data, 'lxml-xml')
        # epub:type="toc" 속성을 가진 <nav> 요소를 찾습니다.
        nav = soup.find("nav", attrs={"epub:type": re.compile(r"toc")})
        if not nav: return []

        def parse_ol(ol_element, depth: int) -> List[Dict[str, Any]]:
            items = []
            # 직계 자식 <li>들만 순회하여 중첩된 목차를 정확히 파싱
            for li in ol_element.find_all("li", recursive=False):
                a = li.find("a", recursive=False)
                if not a: continue
                
                title = a.get_text(" ", strip=True)
                # href 경로를 EPUB 루트 기준의 전체 경로로 변환 (앵커 보존)
                href = self._resolve_href(posixpath.dirname(nav_full_path), a.get("href", ""))
                
                entry = {"title": title, "href": href, "depth": depth, "children": []}
                
                # 중첩된 <ol>이 있으면 재귀 호출
                child_ol = li.find("ol", recursive=False)
                if child_ol:
                    entry["children"] = parse_ol(child_ol, depth + 1)
                items.append(entry)
            return items

        top_ol = nav.find("ol")
        return parse_ol(top_ol, 1) if top_ol else []

    def _parse_toc_ncx(self, data: bytes, ncx_full_path: str) -> List[Dict[str, Any]]:
        """EPUB 2의 .ncx 파일을 파싱하여 목차 트리 구조를 생성합니다."""
        root = etree.fromstring(data)
        ns = {"ncx": "http://www.daisy.org/z3986/2005/ncx/"}
        
        def parse_navpoint(element, depth):
            items = []
            # <navPoint> 요소들을 순회
            for np in element.xpath('ncx:navPoint', namespaces=ns):
                title = np.xpath('string(ncx:navLabel/ncx:text)', namespaces=ns)
                src = np.xpath('string(ncx:content/@src)', namespaces=ns)
                href = self._resolve_href(posixpath.dirname(ncx_full_path), src)
                
                # 재귀적으로 자식 <navPoint>들을 파싱
                entry = {"title": title, "href": href, "depth": depth, "children": parse_navpoint(np, depth + 1)}
                items.append(entry)
            return items

        navmap = root.find('.//ncx:navMap', namespaces=ns)
        return parse_navpoint(navmap, 1) if navmap is not None else []