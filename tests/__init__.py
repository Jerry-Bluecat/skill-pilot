import tempfile
from pathlib import Path


def set_up_home(case, home):
    """公共 setUp：任何写入测试先确认目标是系统临时目录。"""
    case.home = Path(home).resolve()
    temporary = Path(tempfile.gettempdir()).resolve()
    case.assertTrue(case.home.is_relative_to(temporary) and case.home != temporary,
                    '测试主目录必须位于系统临时目录中，禁止写入真实主目录')
