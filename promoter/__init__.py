"""promoter —— 本地低配机器上的「宣传草稿」工具。

设计原则：
1. 本机只负责生成草稿 + push，不直连社交账号；发布全部交给 GitHub Actions。
2. 任何对外文案都必须经过人工 approve（drafts/ -> content/approved/）。
3. 只依赖 Python 标准库，i3 / 16G 无显卡也能秒开。
"""

__version__ = "0.1.0"