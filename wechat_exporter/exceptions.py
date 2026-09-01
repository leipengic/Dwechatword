"""自定义异常体系。"""


class WeChatExporterError(Exception):
    """项目基础异常。"""


class LoginError(WeChatExporterError):
    """登录失败或扫码超时。"""


class SessionExpiredError(WeChatExporterError):
    """登录态失效，需要重新扫码。"""


class RateLimitError(WeChatExporterError):
    """触发微信公众平台频控。"""


class ParseError(WeChatExporterError):
    """文章内容解析失败。"""
