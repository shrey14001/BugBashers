"""
test_cases.py — run AutoFix orchestrator scenarios without hanging silently.

Usage:
  python test_cases.py --known-only          # fast: Chroma + email only
  python test_cases.py --case cakephp_novel_null_property
  AUTOFIX_SKIP_PR=1 python test_cases.py --novel-only   # LLM only, no Bitbucket PR
  python test_cases.py                       # all cases (slow; novel calls Gemini + PR)
"""

import argparse
import os
import sys
import warnings

# Suppress noisy deprecation warnings during batch runs
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", category=FutureWarning)

from autofix.core.orchestrator import Orchestrator

TESTS = {
#     "cakephp_known_1": {
#         "group": "known",
#         "log": """2026-06-04 08:41:02 Error: Fatal error: Call to undefined method Order::findByStatus() in /usr/share/php/Cake_2.10/Cake/Model/Model.php on line 512
# Stack trace:
# #0 /var/sites/demo.bizom.in/app/Controller/OrdersController.php(654): Order->findByStatus(Array)
# #1 /usr/share/php/Cake_2.10/Cake/Controller/Controller.php(491): OrdersController->invokeAction('index', Array)
# #4 {main}""",
#     },
#     "cakephp_known_2": {
#         "group": "known",
#         "log": """2026-06-05 11:00:00 Error: Fatal error: Call to undefined method Order::findByStatus() in /usr/share/php/Cake_2.10/Cake/Model/Model.php on line 512
# Stack trace:
# #0 /var/sites/demo.bizom.in/app/Controller/OrdersController.php(653): Order->findByStatus(array('orderstate_id'=>1))
# #4 {main}""",
#     },
#     "cakephp_novel_wrong_method": {
#         "group": "novel",
#         "note": "Often matches KNOWN (~0.97) — same Model.php:512 embedding",
#         "log": """2026-06-04 09:00:00 Error: Fatal error: Call to undefined method Order::findByState() in /usr/share/php/Cake_2.10/Cake/Model/Model.php on line 512
# Stack trace:
# #0 /var/sites/demo.bizom.in/app/Controller/OrdersController.php(653): Order->findByState(Array)
# #4 {main}""",
    # },
#     "cakephp_novel_null_property": {
#         "group": "novel",
#         "log": """2026-06-04 10:15:33 Error: Fatal error: Call to a member function save() on null in /var/sites/demo.bizom.in/app/Model/Order.php on line 88
# Stack trace:
# #0 /var/sites/demo.bizom.in/app/Controller/OrdersController.php(210): Order->save()
# #1 /usr/share/php/Cake_2.10/Cake/Controller/Controller.php(491): OrdersController->edit()
# #4 {main}""",
#     },
    "cakephp_novel_undefined_index": {
        "group": "novel",
        "log": """2026-06-04 11:22:01 Error: Notice: Undefined index: outlet_id in /var/sites/demo.bizom.in/app/Controller/OutletsController.php on line 145
Stack trace:
#0 /var/sites/demo.bizom.in/app/Controller/OutletsController.php(145): OutletsController->view()
#4 {main}""",
    },
#     "cakephp_novel_missing_class": {
#         "group": "novel",
#         "log": """2026-06-04 12:01:44 Error: Fatal error: Class 'InvalidReportHelper' not found in /var/sites/demo.bizom.in/app/Controller/ReportsController.php on line 32
# Stack trace:
# #0 /var/sites/demo.bizom.in/app/Controller/ReportsController.php(32): ReportsController->index()
# #4 {main}""",
#     },
#     "laravel_novel_function_name": {
#         "group": "novel",
#         "log": (
#             'Function name must be a string {"userId":177,"exception":"[object] (Error(code: 0): '
#             'Function name must be a string at /var/sites/demo.bizom.in/app/laravel/app/'
#             'CompanyManagement/Repositories/OutletRepository.php:14252)\n'
#             '[stacktrace]\n'
#             '#0 /var/sites/demo.bizom.in/app/laravel/app/CompanyManagement/Repositories/'
#             'OutletRepository.php(14215): App\\CompanyManagement\\Repositories\\OutletRepository->getExtraParams()\n'
#             '#1 /var/sites/demo.bizom.in/app/laravel/app/Http/Controllers/'
#             'OutletController.php(1914): App\\CompanyManagement\\Repositories\\OutletRepository->'
#             'getPendingInvoicesMultiDistributorInternal()"}'
#         ),
#     },
#     "unparseable_garbage": {
#         "group": "error",
#         "log": "random text without timestamp or stacktrace",
#     },
}


def main():
    ap = argparse.ArgumentParser(description="Run AutoFix test scenarios")
    ap.add_argument("--known-only", action="store_true", help="Only Chroma known-path tests (fast)")
    ap.add_argument("--novel-only", action="store_true", help="Only novel-path tests (slow)")
    ap.add_argument("--case", help="Run a single test by name")
    args = ap.parse_args()

    if args.case:
        if args.case not in TESTS:
            print(f"Unknown case: {args.case}. Available: {', '.join(TESTS)}")
            sys.exit(1)
        selected = {args.case: TESTS[args.case]}
    elif args.known_only:
        selected = {k: v for k, v in TESTS.items() if v["group"] == "known"}
    elif args.novel_only:
        selected = {k: v for k, v in TESTS.items() if v["group"] == "novel"}
    else:
        selected = TESTS

    skip_pr = os.getenv("AUTOFIX_SKIP_PR", "").lower() in ("1", "true", "yes")
    print(f"Running {len(selected)} case(s). AUTOFIX_SKIP_PR={skip_pr}", flush=True)
    if not skip_pr and args.novel_only:
        print("Tip: novel tests call Gemini + Bitbucket — use AUTOFIX_SKIP_PR=1 to skip PRs.", flush=True)

    o = Orchestrator()
    for name, spec in selected.items():
        print(f"\n{'='*60}\n{name}", flush=True)
        if spec.get("note"):
            print(f"  note: {spec['note']}", flush=True)
        r = o.process(spec["log"], domain="demo.bizom.in")
        print(f"  status={r.status}  similarity={r.similarity}  pr={r.pr_url or '-'}", flush=True)
        if r.detail:
            print(f"  detail={r.detail[:200]}", flush=True)


if __name__ == "__main__":
    main()
