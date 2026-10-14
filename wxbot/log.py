import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("wxbot")

# comtypes/uiautomation 首次运行会生成 COM 缓存并刷一堆 INFO 噪音，压低到 WARNING
logging.getLogger("comtypes").setLevel(logging.WARNING)
