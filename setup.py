from setuptools import find_packages, setup

setup(
    name="btc-ai-paper-trading",
    version="0.1.0",
    description="AI Trading Bot Pro Max Ultra Plus 9000 — FinBERT, CoinGecko technicals, Next.js + FastAPI dashboard",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    python_requires=">=3.9",
    install_requires=[
        "apscheduler>=3.10.0",
        "httpx>=0.27.0",
        "numpy>=1.24.0",
        "pandas>=2.0.0",
        "plotly>=5.18.0",
        "pydantic>=2.0.0",
        "pydantic-settings>=2.0.0",
        "python-dotenv>=1.0.0",
        "torch>=2.0.0",
        "transformers>=4.36.0",
        "yfinance>=0.2.33",
    ],
    entry_points={
        "console_scripts": [
            "btc-paper-run=btc_paper.cli:run_once",
            "btc-paper-scheduler=btc_paper.scheduler.daemon:main",
            "btc-paper-test-news=btc_paper.test_news_sentiment:main",
        ],
    },
)
