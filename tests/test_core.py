# -*- coding: utf-8 -*-
import pytest
import zipfile
import io
from app.core.epub_parser import EpubParser
from app.domain.models import TocItem

# --- 테스트 데이터 ---

CONTAINER_XML = """<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
"""

OPF_EPUB2 = """<?xml version="1.0"?>
<package version="2.0" xmlns="http://www.idpf.org/2007/opf" unique-identifier="book-id">
  <metadata/>
  <manifest>
    <item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>
    <item id="cover" href="cover.xhtml" media-type="application/xhtml+xml"/>
    <item id="chapter1" href="chapter1.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine toc="ncx">
    <itemref idref="cover"/>
    <itemref idref="chapter1"/>
  </spine>
</package>
"""

TOC_NCX = """<?xml version="1.0"?>
<ncx version="2005-1" xmlns="http://www.daisy.org/z3986/2005/ncx/">
  <head/>
  <docTitle><text>Test Book</text></docTitle>
  <navMap>
    <navPoint id="nav1" playOrder="1">
      <navLabel><text>Cover</text></navLabel>
      <content src="cover.xhtml"/>
    </navPoint>
    <navPoint id="nav2" playOrder="2">
      <navLabel><text>Chapter 1</text></navLabel>
      <content src="chapter1.xhtml"/>
      <navPoint id="nav3" playOrder="3">
        <navLabel><text>Section 1.1</text></navLabel>
        <content src="chapter1.xhtml#sec1"/>
      </navPoint>
    </navPoint>
  </navMap>
</ncx>
"""

OPF_EPUB3 = """<?xml version="1.0"?>
<package version="3.0" xmlns="http://www.idpf.org/2007/opf" unique-identifier="book-id">
  <metadata/>
  <manifest>
    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
    <item id="cover" href="cover.xhtml" media-type="application/xhtml+xml"/>
    <item id="chapter1" href="chapter1.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine>
    <itemref idref="cover"/>
    <itemref idref="chapter1"/>
  </spine>
</package>
"""

NAV_XHTML = """<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
<head><title>Navigation</title></head>
<body>
  <nav epub:type="toc" id="toc">
    <ol>
      <li><a href="cover.xhtml">Cover</a></li>
      <li>
        <a href="chapter1.xhtml">Chapter 1</a>
        <ol>
          <li><a href="chapter1.xhtml#sec1">Section 1.1</a></li>
        </ol>
      </li>
    </ol>
  </nav>
</body>
</html>
"""

HTML_CONTENT = "<html><head><title>Test</title></head><body><p>Hello, <b>world</b>!</p></body></html>"

# --- Fixtures ---

@pytest.fixture
def parser():
    """EpubParser의 새 인스턴스를 반환합니다."""
    return EpubParser()

def create_mock_epub(files):
    """파일 경로와 내용을 담은 딕셔너리로부터 메모리 내 zip 파일을 생성합니다."""
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zf:
        for path, content in files.items():
            zf.writestr(path, content)
    zip_buffer.seek(0)
    return zipfile.ZipFile(zip_buffer, "r")

@pytest.fixture
def mock_epub2_zip():
    """EPUB 2 버전에 맞는 가상 EPUB 파일을 생성합니다."""
    return create_mock_epub({
        "META-INF/container.xml": CONTAINER_XML,
        "OEBPS/content.opf": OPF_EPUB2,
        "OEBPS/toc.ncx": TOC_NCX,
    })

@pytest.fixture
def mock_epub3_zip():
    """EPUB 3 버전에 맞는 가상 EPUB 파일을 생성합니다."""
    return create_mock_epub({
        "META-INF/container.xml": CONTAINER_XML,
        "OEBPS/content.opf": OPF_EPUB3,
        "OEBPS/nav.xhtml": NAV_XHTML,
    })

# --- 테스트들 ---

def test_find_opf_path(parser, mock_epub2_zip):
    """container.xml에서 OPF 파일 경로를 정확히 찾는지 테스트합니다."""
    path = parser._find_opf_path(mock_epub2_zip)
    assert path == "OEBPS/content.opf"

def test_get_toc_from_ncx(parser, mock_epub2_zip):
    """EPUB 2의 toc.ncx 파일 파싱을 테스트합니다."""
    opf_path = "OEBPS/content.opf"
    opf_bytes = parser._zip_read(mock_epub2_zip, opf_path)
    manifest, (spine_ids, spine_props) = parser._parse_opf_bytes(opf_bytes)
    
    toc = parser.get_toc_from_stream(mock_epub2_zip, opf_path, manifest, spine_props)
    
    assert len(toc) == 3
    assert toc[0] == TocItem(title="Cover", href="OEBPS/cover.xhtml", level=1)
    assert toc[1] == TocItem(title="Chapter 1", href="OEBPS/chapter1.xhtml", level=1)
    assert toc[2] == TocItem(title="Section 1.1", href="OEBPS/chapter1.xhtml#sec1", level=2)

def test_get_toc_from_nav(parser, mock_epub3_zip):
    """EPUB 3의 nav.xhtml 파일 파싱을 테스트합니다."""
    opf_path = "OEBPS/content.opf"
    opf_bytes = parser._zip_read(mock_epub3_zip, opf_path)
    manifest, (spine_ids, spine_props) = parser._parse_opf_bytes(opf_bytes)
    
    toc = parser.get_toc_from_stream(mock_epub3_zip, opf_path, manifest, spine_props)
    
    assert len(toc) == 3
    assert toc[0] == TocItem(title="Cover", href="OEBPS/cover.xhtml", level=1)
    assert toc[1] == TocItem(title="Chapter 1", href="OEBPS/chapter1.xhtml", level=1)
    assert toc[2] == TocItem(title="Section 1.1", href="OEBPS/chapter1.xhtml#sec1", level=2)

def test_get_plain_text(parser):
    """HTML을 일반 텍스트로 변환하는 기능을 테스트합니다."""
    text = parser.get_plain_text(HTML_CONTENT.encode('utf-8'))
    # lxml의 text_content()는 <title>을 포함한 모든 태그의 텍스트를 추출하며,
    # 요소 주변에 공백을 추가할 수 있습니다.
    expected_text = "Test Hello, world !"
    assert text.strip().replace(" !", "!") == expected_text.strip().replace(" !", "!")

def test_get_toc_returns_empty_list_if_no_toc_file(parser):
    """목차(TOC) 파일이 없을 때 빈 리스트를 반환하는지 테스트합니다."""
    # manifest에 NCX나 NAV 항목이 없는 EPUB 생성
    no_toc_opf = OPF_EPUB2.replace('<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>', '')
    mock_zip = create_mock_epub({
        "META-INF/container.xml": CONTAINER_XML,
        "OEBPS/content.opf": no_toc_opf,
    })
    
    opf_path = "OEBPS/content.opf"
    opf_bytes = parser._zip_read(mock_zip, opf_path)
    manifest, (spine_ids, spine_props) = parser._parse_opf_bytes(opf_bytes)
    
    toc = parser.get_toc_from_stream(mock_zip, opf_path, manifest, spine_props)
    
    assert toc == []
