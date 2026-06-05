from alerting.rule_engine import app
from common.bootstrap import run_bootstrap

def main() -> None:
    run_bootstrap()
    app.main()

if __name__ == '__main__':
    main()
