#!/usr/bin/env python3
"""
FastAPI 应用测试脚本

用途：
- 验证 FastAPI 应用能否正常启动
- 测试基础端点（/health, /）
- 检查数据库连接
"""

import sys
import json
from app.main import app
from fastapi.testclient import TestClient

# 创建测试客户端
client = TestClient(app)


def test_app_info():
    """测试应用信息"""
    print("📝 应用信息")
    print(f"  标题: {app.title}")
    print(f"  版本: {app.version}")
    print()


def test_root_endpoint():
    """测试根路由 /"""
    print("🔍 测试 GET /")
    response = client.get("/")
    print(f"  状态码: {response.status_code}")
    print(f"  响应: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")
    assert response.status_code == 200
    print("  ✅ 通过\n")


def test_health_endpoint():
    """测试健康检查 /health"""
    print("🔍 测试 GET /health")
    response = client.get("/health")
    print(f"  状态码: {response.status_code}")
    print(f"  响应: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
    print("  ✅ 通过\n")


def test_swagger_docs():
    """测试 Swagger 文档"""
    print("🔍 测试 GET /docs")
    response = client.get("/docs")
    print(f"  状态码: {response.status_code}")
    assert response.status_code == 200
    print("  ✅ Swagger UI 可访问\n")


def test_redoc():
    """测试 ReDoc 文档"""
    print("🔍 测试 GET /redoc")
    response = client.get("/redoc")
    print(f"  状态码: {response.status_code}")
    assert response.status_code == 200
    print("  ✅ ReDoc 可访问\n")


def test_database_init():
    """测试数据库初始化"""
    print("🔍 测试数据库初始化")
    try:
        from app.models import SessionLocal, Trade, AlertRule, init_db

        # 初始化数据库表（创建所有表）
        init_db()

        # 测试创建会话
        db = SessionLocal()

        # 查询表是否存在
        trade_count = db.query(Trade).count()
        alert_count = db.query(AlertRule).count()

        print(f"  Trade 表记录数: {trade_count}")
        print(f"  AlertRule 表记录数: {alert_count}")
        print("  ✅ 数据库连接正常\n")

        db.close()
    except Exception as e:
        print(f"  ❌ 数据库初始化失败: {e}\n")
        raise


def test_routes():
    """列出所有已注册路由"""
    print("📋 已注册路由")
    for route in app.routes:
        if hasattr(route, 'path'):
            methods = ', '.join(route.methods) if hasattr(route, 'methods') else 'GET'
            print(f"  {route.path:<30} {methods}")
    print()


def test_progress_capture():
    """测试进度条捕获逻辑"""
    print("🔍 测试进度条捕获")

    import io
    import threading
    from app.data_fetcher.cache_manager import _StderrCapture, _progress_map, _progress_lock

    # 清空全局进度字典
    with _progress_lock:
        _progress_map.clear()

    # 创建模拟 stderr
    mock_stderr = io.StringIO()
    capture = _StderrCapture("A股全市场行情", mock_stderr)

    # 测试用例：tqdm 进度条格式
    # 注意：.strip() 会删除前导空格，所以期望值也是 strip 后的
    test_cases = [
        ("  7%|6         | 4/58 [00:32<07:22,  8.19s/it]\r", "7%|6         | 4/58 [00:32<07:22,  8.19s/it]"),
        (" 29%|##8       | 4/14 [00:32<01:19,  7.94s/it]\r", "29%|##8       | 4/14 [00:32<01:19,  7.94s/it]"),
        ("100%|##########| 58/58 [05:48<00:00,  6.04s/it]\n", "100%|##########| 58/58 [05:48<00:00,  6.04s/it]"),
    ]

    for input_str, expected_progress in test_cases:
        print(f"  输入: {repr(input_str)}")
        capture.write(input_str)

        # 检查是否被正确捕获（从全局进度字典）
        with _progress_lock:
            captured = _progress_map.get("A股全市场行情", "")

        print(f"  捕获: {repr(captured)}")
        assert captured == expected_progress, f"期望 {repr(expected_progress)}，得到 {repr(captured)}"
        print(f"  ✅ 通过")

    print("  ✅ 进度条捕获测试通过\n")


if __name__ == "__main__":
    print("=" * 60)
    print("🧪 FastAPI 应用测试")
    print("=" * 60)
    print()

    try:
        test_app_info()
        test_routes()
        test_progress_capture()
        test_root_endpoint()
        test_health_endpoint()
        test_swagger_docs()
        test_redoc()
        test_database_init()

        print("=" * 60)
        print("✅ 所有测试通过！")
        print("=" * 60)
        print()
        print("🚀 启动应用的命令：")
        print("   python3 -m uvicorn app.main:app --reload")
        print()
        print("📖 文档链接：")
        print("   - Swagger UI: http://localhost:8000/docs")
        print("   - ReDoc: http://localhost:8000/redoc")
        print()

    except AssertionError as e:
        print()
        print("=" * 60)
        print(f"❌ 测试失败: {e}")
        print("=" * 60)
        sys.exit(1)
    except Exception as e:
        print()
        print("=" * 60)
        print(f"❌ 发生错误: {e}")
        print("=" * 60)
        import traceback
        traceback.print_exc()
        sys.exit(1)
