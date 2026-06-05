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

    # ── Laravel novel cases ────────────────────────────────────────────────────

    # "laravel_undefined_offset_task": {
    #     "group": "novel",
    #     "note": "bindu.bizom.in — Undefined offset in TaskRepository",
    #     "log": (
    #         'Undefined offset: 2866 {"userId":2866,"exception":"[object] (ErrorException(code: 0): '
    #         'Undefined offset: 2866 at /var/sites/bindu.bizom.in/app/laravel/app/Modules/'
    #         'TaskManagement/Repositories/TaskRepository.php:9152)\n'
    #         '[stacktrace]\n'
    #         '#0 /var/sites/bindu.bizom.in/app/laravel/app/Modules/TaskManagement/Repositories/'
    #         'TaskRepository.php(9152): Illuminate\\\\Foundation\\\\Bootstrap\\\\HandleExceptions->handleError()\n'
    #         '#1 /var/sites/bindu.bizom.in/app/laravel/app/Http/Controllers/TaskController.php(816): '
    #         'App\\\\Modules\\\\TaskManagement\\\\Repositories\\\\TaskRepository->jointWorking()\n'
    #         '#2 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/'
    #         'Routing/Controller.php(54): App\\\\Http\\\\Controllers\\\\TaskController->jointWorking()"}'
    #     ),
    # },

    # "laravel_type_error_int_string_order": {
    #     "group": "novel",
    #     "note": "crax.bizom.in — int expected, string given in OrderRepository",
    #     "log": (
    #         'Argument 1 passed to App\\TransactionManagement\\Repositories\\OrderRepository::'
    #         'getLatestOrders() must be of the type int, string given, called in '
    #         '/var/sites/crax.bizom.in/app/laravel/app/CompanyManagement/Repositories/'
    #         'OutletRepository.php on line 2830 {"userId":15829,"exception":"[object] '
    #         '(TypeError(code: 0): Argument 1 passed to App\\\\TransactionManagement\\\\Repositories\\\\'
    #         'OrderRepository::getLatestOrders() must be of the type int, string given, called in '
    #         '/var/sites/crax.bizom.in/app/laravel/app/CompanyManagement/Repositories/'
    #         'OutletRepository.php on line 2830 at /var/sites/crax.bizom.in/app/laravel/app/'
    #         'TransactionManagement/Repositories/OrderRepository.php:93)\n'
    #         '[stacktrace]\n'
    #         '#0 /var/sites/crax.bizom.in/app/laravel/app/CompanyManagement/Repositories/'
    #         'OutletRepository.php(2830): App\\\\TransactionManagement\\\\Repositories\\\\'
    #         'OrderRepository->getLatestOrders()\n'
    #         '#1 /var/sites/crax.bizom.in/app/laravel/app/CompanyManagement/Repositories/'
    #         'OutletRepository.php(2621): App\\\\CompanyManagement\\\\Repositories\\\\'
    #         'OutletRepository->getOutletReportData()\n'
    #         '#5 /var/sites/crax.bizom.in/app/laravel/app/Http/Controllers/OutletController.php(373): '
    #         'App\\\\CompanyManagement\\\\Repositories\\\\OutletRepository->getOutletsInfoInternal()"}'
    #     ),
    # },

    # "laravel_undefined_index_sale_call": {
    #     "group": "novel",
    #     "note": "glas.bizom.in — Undefined index: sale in CallRepository",
    #     "log": (
    #         'Undefined index: sale {"userId":480,"exception":"[object] (ErrorException(code: 0): '
    #         'Undefined index: sale at /var/sites/glas.bizom.in/app/laravel/app/'
    #         'TransactionManagement/Repositories/CallRepository.php:4621)\n'
    #         '[stacktrace]\n'
    #         '#0 /var/sites/glas.bizom.in/app/laravel/app/TransactionManagement/Repositories/'
    #         'CallRepository.php(4621): Illuminate\\\\Foundation\\\\Bootstrap\\\\HandleExceptions->handleError()\n'
    #         '#1 /var/sites/glas.bizom.in/app/laravel/app/Http/Controllers/CallController.php(118): '
    #         'App\\\\TransactionManagement\\\\Repositories\\\\CallRepository->perFormanceForUserInternal()\n'
    #         '#2 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/'
    #         'Routing/Controller.php(54): App\\\\Http\\\\Controllers\\\\CallController->performanceForUser()"}'
    #     ),
    # },

    # "laravel_type_error_array_null_outlet": {
    #     "group": "novel",
    #     "note": "bajajelectricals.bizom.in — array expected, null given in CommonUtils",
    #     "log": (
    #         'Argument 1 passed to App\\Utils\\CommonUtils::convertToObject() must be of the type '
    #         'array, null given, called in /var/sites/bajajelectricals.bizom.in/app/laravel/app/'
    #         'Http/Controllers/OutletController.php on line 189 {"userId":9122,"exception":"[object] '
    #         '(TypeError(code: 0): Argument 1 passed to App\\\\Utils\\\\CommonUtils::convertToObject() '
    #         'must be of the type array, null given, called in /var/sites/bajajelectricals.bizom.in/'
    #         'app/laravel/app/Http/Controllers/OutletController.php on line 189 at '
    #         '/var/sites/bajajelectricals.bizom.in/app/laravel/app/Utils/CommonUtils.php:1801)\n'
    #         '[stacktrace]\n'
    #         '#0 /var/sites/bajajelectricals.bizom.in/app/laravel/app/Http/Controllers/'
    #         'OutletController.php(189): App\\\\Utils\\\\CommonUtils::convertToObject()\n'
    #         '#1 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/'
    #         'Routing/Controller.php(54): App\\\\Http\\\\Controllers\\\\OutletController->edit()"}'
    #     ),
    # },

    # "laravel_array_merge_object_call": {
    #     "group": "novel",
    #     "note": "sidsfarm.bizom.in — array_merge got object in CallRepository",
    #     "log": (
    #         'array_merge(): Expected parameter 1 to be an array, object given {"userId":41,'
    #         '"exception":"[object] (ErrorException(code: 0): array_merge(): Expected parameter 1 '
    #         'to be an array, object given at /var/sites/sidsfarm.bizom.in/app/laravel/app/'
    #         'TransactionManagement/Repositories/CallRepository.php:1512)\n'
    #         '[stacktrace]\n'
    #         '#0 [internal function]: Illuminate\\\\Foundation\\\\Bootstrap\\\\HandleExceptions->handleError()\n'
    #         '#1 /var/sites/sidsfarm.bizom.in/app/laravel/app/TransactionManagement/Repositories/'
    #         'CallRepository.php(1512): array_merge()\n'
    #         '#2 /var/sites/sidsfarm.bizom.in/app/laravel/app/Http/Controllers/CallController.php(165): '
    #         'App\\\\TransactionManagement\\\\Repositories\\\\CallRepository->getMyCallsInternal()\n'
    #         '#3 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/'
    #         'Routing/Controller.php(54): App\\\\Http\\\\Controllers\\\\CallController->getMycalls()"}'
    #     ),
    # },

    # "laravel_undefined_index_freeskuprice": {
    #     "group": "novel",
    #     "note": "g-next-mt.bizom.in — Undefined index: freeskuprice in PaymentSaleService",
    #     "log": (
    #         'Undefined index: freeskuprice {"userId":320,"exception":"[object] (ErrorException(code: 0): '
    #         'Undefined index: freeskuprice at /var/sites/g-next-mt.bizom.in/app/laravel/app/'
    #         'TransactionManagement/Services/PaymentSaleService.php:1080)\n'
    #         '[stacktrace]\n'
    #         '#0 /var/sites/g-next-mt.bizom.in/app/laravel/app/TransactionManagement/Services/'
    #         'PaymentSaleService.php(1080): Illuminate\\\\Foundation\\\\Bootstrap\\\\HandleExceptions->handleError()\n'
    #         '#1 /var/sites/g-next-mt.bizom.in/app/laravel/app/TransactionManagement/Services/'
    #         'PaymentSaleService.php(614): App\\\\TransactionManagement\\\\Services\\\\'
    #         'PaymentSaleService->initSettingProperties()\n'
    #         '#2 /var/sites/g-next-mt.bizom.in/app/laravel/app/TransactionManagement/Repositories/'
    #         'PaymentRepository.php(25136): App\\\\TransactionManagement\\\\Services\\\\'
    #         'PaymentSaleService->saveSale()\n'
    #         '#3 /var/sites/g-next-mt.bizom.in/app/laravel/app/Http/Controllers/'
    #         'PaymentController.php(1032): App\\\\TransactionManagement\\\\Repositories\\\\'
    #         'PaymentRepository->addPrimarySale()"}'
    #     ),
    # },

    # # ── Duplicate pair — tests the KNOWN dedup path ────────────────────────────
    # # First occurrence is novel (generates fix + PR), second should be caught as KNOWN.

    # "laravel_sql_fordate_like_novel": {
    #     "group": "novel",
    #     "note": "esskaybeauty.bizom.in — SQLSTATE column not found (first occurrence → novel)",
    #     "log": (
    #         "SQLSTATE[42S22]: Column not found: 1054 Unknown column 'Payment.fordate LIKE' in "
    #         "'where clause' {\"userId\":283,\"exception\":\"[object] (Illuminate\\\\Database\\\\"
    #         "QueryException(code: 42S22): SQLSTATE[42S22]: Column not found: 1054 Unknown column "
    #         "'Payment.fordate LIKE' in 'where clause' at /usr/share/vendor_bizom/laravel/"
    #         "laravel_8_20251024/laravel/framework/src/Illuminate/Database/Connection.php:712)\n"
    #         "[stacktrace]\n"
    #         "#0 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/"
    #         "Database/Connection.php(672): Illuminate\\\\Database\\\\Connection->runQueryCallback()\n"
    #         "#12 /var/sites/esskaybeauty.bizom.in/app/laravel/app/TransactionManagement/Repositories/"
    #         "PaymentRepository.php(14255): Yajra\\\\DataTables\\\\QueryDataTable->make()\n"
    #         "#13 /var/sites/esskaybeauty.bizom.in/app/laravel/app/Http/Controllers/"
    #         "PaymentController.php(715): App\\\\TransactionManagement\\\\Repositories\\\\"
    #         "PaymentRepository->getInvoicesForReturnInternal()\"}"
    #     ),
    # },

    "laravel_sql_fordate_like_known": {
        "group": "known",
        "note": "pureplaydms.bizom.in — same SQLSTATE error, different domain (should be KNOWN)",
        "log": (
            "SQLSTATE[42S22]: Column not found: 1054 Unknown column 'Payment.fordate LIKE' in "
            "'where clause' {\"userId\":697,\"exception\":\"[object] (Illuminate\\\\Database\\\\"
            "QueryException(code: 42S22): SQLSTATE[42S22]: Column not found: 1054 Unknown column "
            "'Payment.fordate LIKE' in 'where clause' at /usr/share/vendor_bizom/laravel/"
            "laravel_8_20251024/laravel/framework/src/Illuminate/Database/Connection.php:712)\n"
            "[stacktrace]\n"
            "#0 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/"
            "Database/Connection.php(672): Illuminate\\\\Database\\\\Connection->runQueryCallback()\n"
            "#12 /var/sites/pureplaydms.bizom.in/app/laravel/app/TransactionManagement/Repositories/"
            "PaymentRepository.php(14225): Yajra\\\\DataTables\\\\QueryDataTable->make()\n"
            "#13 /var/sites/pureplaydms.bizom.in/app/laravel/app/Http/Controllers/"
            "PaymentController.php(715): App\\\\TransactionManagement\\\\Repositories\\\\"
            "PaymentRepository->getInvoicesForReturnInternal()\"}"
        ),
    },

    # # ── CakePHP2 novel case ────────────────────────────────────────────────────

    # "cakephp_argument_count_claims": {
    #     "group": "novel",
    #     "note": "happilo.bizom.in — too few arguments to ClaimsController::deleteClaimFromCart()",
    #     "log": (
    #         "Error: [ArgumentCountError] Too few arguments to function "
    #         "ClaimsController::deleteClaimFromCart(), 0 passed and exactly 1 expected\n"
    #         "Request URL: /claims/deleteClaimFromCart\n"
    #         "Stack Trace:\n"
    #         "#0 [internal function]: ClaimsController->deleteClaimFromCart()\n"
    #         "#1 /usr/share/php/Cake_2.10/Cake/Controller/Controller.php(499): ReflectionMethod->invokeArgs()\n"
    #         "#2 /usr/share/php/Cake_2.10/Cake/Routing/Dispatcher.php(193): Controller->invokeAction()\n"
    #         "#3 /usr/share/php/Cake_2.10/Cake/Routing/Dispatcher.php(167): Dispatcher->_invoke()\n"
    #         "#4 /var/sites/happilo.bizom.in/app/webroot/index.php(161): Dispatcher->dispatch()\n"
    #         "#5 {main}"
    #     ),
    # },
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
        r = o.process(spec["log"], domain=spec.get("domain"))  # None = let parser extract from log
        print(f"  status={r.status}  similarity={r.similarity}  pr={r.pr_url or '-'}", flush=True)
        if r.detail:
            print(f"  detail={r.detail[:200]}", flush=True)


if __name__ == "__main__":
    main()
