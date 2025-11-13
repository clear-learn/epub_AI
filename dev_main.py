# -*- coding: utf-8 -*-
# dev_main.py  (개발용으로만 사용)
import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "app.api.endpoints:app",
        host="0.0.0.0",
        port=18000,
        reload=True,     # 개발: 코드 변경 자동 반영
        workers=1
    )
