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

    # "laravel_novel_sql_column_not_found": {
    #     "group": "novel",
    #     "domain": "drumsfood.bizom.in",
    #     "log": (
    #         "SQLSTATE[42S22]: Column not found: 1054 Unknown column "
    #         "'Activitypicture.activity_id' in 'field list' "
    #         '{"userId":166,"exception":"[object] '
    #         "(Illuminate\\Database\\QueryException(code: 42S22): "
    #         "SQLSTATE[42S22]: Column not found: 1054 Unknown column "
    #         "'Activitypicture.activity_id' in 'field list' "
    #         "(SQL: select Activitypicture.activity_id AS Activitypicture__activity_id, "
    #         "Activitypicture.id AS Activitypicture__id from `activitypictures` as `ActivityPicture` where (0 = 1)) "
    #         "at /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework"
    #         "/src/Illuminate/Database/Connection.php:712)\n"
    #         "[stacktrace]\n"
    #         "#0 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework"
    #         "/src/Illuminate/Database/Connection.php(672): Illuminate\\Database\\Connection->runQueryCallback()\n"
    #         "#1 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework"
    #         "/src/Illuminate/Database/Connection.php(376): Illuminate\\Database\\Connection->run()\n"
    #         "#2 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework"
    #         "/src/Illuminate/Database/Query/Builder.php(2414): Illuminate\\Database\\Connection->select()\n"
    #         "#3 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework"
    #         "/src/Illuminate/Database/Query/Builder.php(2402): Illuminate\\Database\\Query\\Builder->runSelect()\n"
    #         "#4 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework"
    #         "/src/Illuminate/Database/Query/Builder.php(2936): Illuminate\\Database\\Query\\Builder->Illuminate\\Database\\Query\\{closure}()\n"
    #         "#5 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework"
    #         "/src/Illuminate/Database/Query/Builder.php(2403): Illuminate\\Database\\Query\\Builder->onceWithColumns()\n"
    #         "#6 /var/sites/drumsfood.bizom.in/app/laravel/app/Http/Traits/"
    #         "LaravelFindORMTrait.php(239): Illuminate\\Database\\Query\\Builder->get()\n"
    #         "#7 [internal function]: App\\Models\\BaseModel->findLaravel()\n"
    #         "#8 /var/sites/drumsfood.bizom.in/app/laravel/app/Modules/CommonManagement/"
    #         "Repositories/ActivityPicturesRepository.php(36): call_user_func_array()\n"
    #         "#9 /var/sites/drumsfood.bizom.in/app/laravel/app/Modules/ReportManagement/"
    #         "Repositories/ReportRepository.php(1986): App\\Modules\\CommonManagement\\Repositories\\ActivityPicturesRepository->__call()\n"
    #         "#10 /var/sites/drumsfood.bizom.in/app/laravel/app/Modules/ReportManagement/"
    #         "Repositories/ReportRepository.php(4626): App\\Modules\\ReportManagement\\Repositories\\ReportRepository->getActivitypics()\n"
    #         "#11 /var/sites/drumsfood.bizom.in/app/laravel/app/Http/Controllers/"
    #         "ReportController.php(243): App\\Modules\\ReportManagement\\Repositories\\ReportRepository->newIndexWithDateDownloadXlsInternal()"
    #         '"}'
    #     ),
    # },

# "laravel_array_merge_object_call_devext": {
#   "group": "novel",
#   "fingerprint": "5e8c7b3a9f2d1e4c6a8b0f3d7e9c2a4b6d8f0e1a2b3c4d5e6f7a8b9c0d1e2f3a4",
#   "tenant": "devextqaenv",
#   "error": "array_merge(): Expected parameter 1 to be an array, object given",
#   "stack_trace": "#0 [internal function]: Illuminate\\Foundation\\Bootstrap\\HandleExceptions->handleError()\n#1 /var/sites/devextqaenv.bizomdev.in/app/laravel/app/TransactionManagement/Repositories/CallRepository.php(1513): array_merge()\n#2 /var/sites/devextqaenv.bizomdev.in/app/laravel/app/Http/Controllers/CallController.php(165): App\\TransactionManagement\\Repositories\\CallRepository->getMyCallsInternal()\n#3 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Routing/Controller.php(54): App\\Http\\Controllers\\CallController->getMycalls()\n#4 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Routing/ControllerDispatcher.php(45): Illuminate\\Routing\\Controller->callAction()\n#5 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Routing/Route.php(262): Illuminate\\Routing\\ControllerDispatcher->dispatch()\n#6 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Routing/Route.php(205): Illuminate\\Routing\\Route->runController()\n#7 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Routing/Router.php(721): Illuminate\\Routing\\Route->run()\n#8 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Pipeline/Pipeline.php(128): Illuminate\\Routing\\Router->Illuminate\\Routing\\{closure}()\n#9 /var/sites/devextqaenv.bizomdev.in/app/laravel/app/Http/Middleware/SetDatabaseConnection.php(86): Illuminate\\Pipeline\\Pipeline->Illuminate\\Pipeline\\{closure}()\n#10 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Pipeline/Pipeline.php(167): App\\Http\\Middleware\\SetDatabaseConnection->handle()\n#11 /usr/share/vendor_bizom/laravel/laravel_8_20251024/inertiajs/inertia-laravel/src/Middleware.php(87): Illuminate\\Pipeline\\Pipeline->Illuminate\\Pipeline\\{closure}()\n#12 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Pipeline/Pipeline.php(167): Inertia\\Middleware->handle()\n#13 /var/sites/devextqaenv.bizomdev.in/app/laravel/app/Http/Middleware/CheckPortalConfiguration.php(59): Illuminate\\Pipeline\\Pipeline->Illuminate\\Pipeline\\{closure}()\n#14 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Pipeline/Pipeline.php(167): App\\Http\\Middleware\\CheckPortalConfiguration->handle()\n#15 /var/sites/devextqaenv.bizomdev.in/app/laravel/app/Http/Middleware/LogQueriesPerAction.php(17): Illuminate\\Pipeline\\Pipeline->Illuminate\\Pipeline\\{closure}()\n#16 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Pipeline/Pipeline.php(167): App\\Http\\Middleware\\LogQueriesPerAction->handle()\n#17 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Routing/Middleware/SubstituteBindings.php(50): Illuminate\\Pipeline\\Pipeline->Illuminate\\Pipeline\\{closure}()\n#18 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Pipeline/Pipeline.php(167): Illuminate\\Routing\\Middleware\\SubstituteBindings->handle()\n#19 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Auth/Middleware/Authenticate.php(44): Illuminate\\Pipeline\\Pipeline->Illuminate\\Pipeline\\{closure}()\n#20 /var/sites/devextqaenv.bizomdev.in/app/laravel/app/Http/Middleware/Authenticate.php(30): Illuminate\\Auth\\Middleware\\Authenticate->handle()\n#21 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Pipeline/Pipeline.php(167): App\\Http\\Middleware\\Authenticate->handle()\n#22 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Foundation/Http/Middleware/VerifyCsrfToken.php(78): Illuminate\\Pipeline\\Pipeline->Illuminate\\Pipeline\\{closure}()\n#23 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Pipeline/Pipeline.php(167): Illuminate\\Foundation\\Http\\Middleware\\VerifyCsrfToken->handle()\n#24 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/View/Middleware/ShareErrorsFromSession.php(49): Illuminate\\Pipeline\\Pipeline->Illuminate\\Pipeline\\{closure}()\n#25 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Pipeline/Pipeline.php(167): Illuminate\\View\\Middleware\\ShareErrorsFromSession->handle()\n#26 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Session/Middleware/StartSession.php(121): Illuminate\\Pipeline\\Pipeline->Illuminate\\Pipeline\\{closure}()\n#27 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Session/Middleware/StartSession.php(64): Illuminate\\Session\\Middleware\\StartSession->handleStatefulRequest()\n#28 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Pipeline/Pipeline.php(167): Illuminate\\Session\\Middleware\\StartSession->handle()\n#29 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Cookie/Middleware/AddQueuedCookiesToResponse.php(37): Illuminate\\Pipeline\\Pipeline->Illuminate\\Pipeline\\{closure}()\n#30 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Pipeline/Pipeline.php(167): Illuminate\\Cookie\\Middleware\\AddQueuedCookiesToResponse->handle()\n#31 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Cookie/Middleware/EncryptCookies.php(67): Illuminate\\Pipeline\\Pipeline->Illuminate\\Pipeline\\{closure}()\n#32 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Pipeline/Pipeline.php(167): Illuminate\\Cookie\\Middleware\\EncryptCookies->handle()\n#33 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Pipeline/Pipeline.php(103): Illuminate\\Pipeline\\Pipeline->Illuminate\\Pipeline\\{closure}()\n#34 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Routing/Router.php(723): Illuminate\\Pipeline\\Pipeline->then()\n#35 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Routing/Router.php(698): Illuminate\\Routing\\Router->runRouteWithinStack()\n#36 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Routing/Router.php(662): Illuminate\\Routing\\Router->runRoute()\n#37 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Routing/Router.php(651): Illuminate\\Routing\\Router->dispatchToRoute()\n#38 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Foundation/Http/Kernel.php(167): Illuminate\\Routing\\Router->dispatch()\n#39 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Pipeline/Pipeline.php(128): Illuminate\\Foundation\\Http\\Kernel->Illuminate\\Foundation\\Http\\{closure}()\n#40 /var/sites/devextqaenv.bizomdev.in/app/laravel/app/Http/Middleware/SetDatabaseConnection.php(86): Illuminate\\Pipeline\\Pipeline->Illuminate\\Pipeline\\{closure}()\n#41 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Pipeline/Pipeline.php(167): App\\Http\\Middleware\\SetDatabaseConnection->handle()\n#42 /var/sites/devextqaenv.bizomdev.in/app/laravel/app/Http/Middleware/ClearOutputBuffer.php(23): Illuminate\\Pipeline\\Pipeline->Illuminate\\Pipeline\\{closure}()\n#43 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Pipeline/Pipeline.php(167): App\\Http\\Middleware\\ClearOutputBuffer->handle()\n#44 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Foundation/Http/Middleware/TransformsRequest.php(21): Illuminate\\Pipeline\\Pipeline->Illuminate\\Pipeline\\{closure}()\n#45 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Foundation/Http/Middleware/ConvertEmptyStringsToNull.php(31): Illuminate\\Foundation\\Http\\Middleware\\TransformsRequest->handle()\n#46 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Pipeline/Pipeline.php(167): Illuminate\\Foundation\\Http\\Middleware\\ConvertEmptyStringsToNull->handle()\n#47 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Foundation/Http/Middleware/TransformsRequest.php(21): Illuminate\\Pipeline\\Pipeline->Illuminate\\Pipeline\\{closure}()\n#48 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Foundation/Http/Middleware/TrimStrings.php(40): Illuminate\\Foundation\\Http\\Middleware\\TransformsRequest->handle()\n#49 /var/sites/devextqaenv.bizomdev.in/app/laravel/app/Http/Middleware/TrimStrings.php(26): Illuminate\\Foundation\\Http\\Middleware\\TrimStrings->handle()\n#50 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Pipeline/Pipeline.php(167): App\\Http\\Middleware\\TrimStrings->handle()\n#51 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Foundation/Http/Middleware/ValidatePostSize.php(27): Illuminate\\Pipeline\\Pipeline->Illuminate\\Pipeline\\{closure}()\n#52 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Pipeline/Pipeline.php(167): Illuminate\\Foundation\\Http\\Middleware\\ValidatePostSize->handle()\n#53 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Foundation/Http/Middleware/PreventRequestsDuringMaintenance.php(86): Illuminate\\Pipeline\\Pipeline->Illuminate\\Pipeline\\{closure}()\n#54 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Pipeline/Pipeline.php(167): Illuminate\\Foundation\\Http\\Middleware\\PreventRequestsDuringMaintenance->handle()\n#55 /usr/share/vendor_bizom/laravel/laravel_8_20251024/fruitcake/laravel-cors/src/HandleCors.php(38): Illuminate\\Pipeline\\Pipeline->Illuminate\\Pipeline\\{closure}()\n#56 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Pipeline/Pipeline.php(167): Fruitcake\\Cors\\HandleCors->handle()\n#57 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Http/Middleware/TrustProxies.php(39): Illuminate\\Pipeline\\Pipeline->Illuminate\\Pipeline\\{closure}()\n#58 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Pipeline/Pipeline.php(167): Illuminate\\Http\\Middleware\\TrustProxies->handle()\n#59 /var/sites/devextqaenv.bizomdev.in/app/laravel/app/Http/Middleware/NormalizeUrlSlashes.php(41): Illuminate\\Pipeline\\Pipeline->Illuminate\\Pipeline\\{closure}()\n#60 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Pipeline/Pipeline.php(167): App\\Http\\Middleware\\NormalizeUrlSlashes->handle()\n#61 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Pipeline/Pipeline.php(103): Illuminate\\Pipeline\\Pipeline->Illuminate\\Pipeline\\{closure}()\n#62 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Foundation/Http/Kernel.php(142): Illuminate\\Pipeline\\Pipeline->then()\n#63 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Foundation/Http/Kernel.php(111): Illuminate\\Foundation\\Http\\Kernel->sendRequestThroughRouter()\n#64 /var/sites/devextqaenv.bizomdev.in/app/laravel/public/index.php(51): Illuminate\\Foundation\\Http\\Kernel->handle()\n#65 /var/sites/devextqaenv.bizomdev.in/app/webroot/index.php(14): require_once('/var/sites/deve...')\n#66 {main}",
#   "exception_class": "ErrorException",
#   "category": "TypeError",
#   "status_code": 500,
#   "endpoint": "/calls/getmycalls",
#   "framework": "laravel",
#   "source_file": "/var/sites/devextqaenv.bizomdev.in/app/laravel/app/TransactionManagement/Repositories/CallRepository.php",
#   "first_seen_at": "2026-05-01T11:02:40Z"
# },
"laravel_array_merge_object_call_devext":{
  "fingerprint": "a7c3e5f8b9d2a4c6e8f0b1d3f5a7c9e2b4d6f8a0c2e4f6a8b0d2f4a6c8e0f2a4c6",
  "tenant": "devmilanmobile",
  "error": "syntax error, unexpected '}', expecting ';'",
  "stack_trace": "#0 /usr/share/vendor_bizom/laravel/laravel_8_20251024/composer/ClassLoader.php(427): Composer\\Autoload\\{closure}()\n#1 [internal function]: Composer\\Autoload\\ClassLoader->loadClass()\n#2 [internal function]: spl_autoload_call()\n#3 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Container/Container.php(877): ReflectionClass->__construct()\n#4 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Container/Container.php(758): Illuminate\\Container\\Container->build()\n#5 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Foundation/Application.php(851): Illuminate\\Container\\Container->resolve()\n#6 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Container/Container.php(694): Illuminate\\Foundation\\Application->resolve()\n#7 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Foundation/Application.php(836): Illuminate\\Container\\Container->make()\n#8 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Routing/Route.php(276): Illuminate\\Foundation\\Application->make()\n#9 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Routing/Route.php(1080): Illuminate\\Routing\\Route->getController()\n#10 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Routing/Route.php(1023): Illuminate\\Routing\\Route->controllerMiddleware()\n#11 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Routing/Router.php(734): Illuminate\\Routing\\Route->gatherMiddleware()\n#12 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Routing/Router.php(714): Illuminate\\Routing\\Router->gatherRouteMiddleware()\n#13 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Routing/Router.php(698): Illuminate\\Routing\\Router->runRouteWithinStack()\n#14 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Routing/Router.php(662): Illuminate\\Routing\\Router->runRoute()\n#15 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Routing/Router.php(651): Illuminate\\Routing\\Router->dispatchToRoute()\n#16 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Foundation/Http/Kernel.php(167): Illuminate\\Routing\\Router->dispatch()\n#17 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Pipeline/Pipeline.php(128): Illuminate\\Foundation\\Http\\Kernel->Illuminate\\Foundation\\Http\\{closure}()\n#18 /var/sites/devmilanmobile.bizomdev.in/app/laravel/app/Http/Middleware/SetDatabaseConnection.php(86): Illuminate\\Pipeline\\Pipeline->Illuminate\\Pipeline\\{closure}()\n#19 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Pipeline/Pipeline.php(167): App\\Http\\Middleware\\SetDatabaseConnection->handle()\n#20 /var/sites/devmilanmobile.bizomdev.in/app/laravel/app/Http/Middleware/ClearOutputBuffer.php(23): Illuminate\\Pipeline\\Pipeline->Illuminate\\Pipeline\\{closure}()\n#21 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Pipeline/Pipeline.php(167): App\\Http\\Middleware\\ClearOutputBuffer->handle()\n#22 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Foundation/Http/Middleware/TransformsRequest.php(21): Illuminate\\Pipeline\\Pipeline->Illuminate\\Pipeline\\{closure}()\n#23 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Foundation/Http/Middleware/ConvertEmptyStringsToNull.php(31): Illuminate\\Foundation\\Http\\Middleware\\TransformsRequest->handle()\n#24 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Pipeline/Pipeline.php(167): Illuminate\\Foundation\\Http\\Middleware\\ConvertEmptyStringsToNull->handle()\n#25 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Foundation/Http/Middleware/TransformsRequest.php(21): Illuminate\\Pipeline\\Pipeline->Illuminate\\Pipeline\\{closure}()\n#26 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Foundation/Http/Middleware/TrimStrings.php(40): Illuminate\\Foundation\\Http\\Middleware\\TransformsRequest->handle()\n#27 /var/sites/devmilanmobile.bizomdev.in/app/laravel/app/Http/Middleware/TrimStrings.php(26): Illuminate\\Foundation\\Http\\Middleware\\TrimStrings->handle()\n#28 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Pipeline/Pipeline.php(167): App\\Http\\Middleware\\TrimStrings->handle()\n#29 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Foundation/Http/Middleware/ValidatePostSize.php(27): Illuminate\\Pipeline\\Pipeline->Illuminate\\Pipeline\\{closure}()\n#30 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Pipeline/Pipeline.php(167): Illuminate\\Foundation\\Http\\Middleware\\ValidatePostSize->handle()\n#31 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Foundation/Http/Middleware/PreventRequestsDuringMaintenance.php(86): Illuminate\\Pipeline\\Pipeline->Illuminate\\Pipeline\\{closure}()\n#32 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Pipeline/Pipeline.php(167): Illuminate\\Foundation\\Http\\Middleware\\PreventRequestsDuringMaintenance->handle()\n#33 /usr/share/vendor_bizom/laravel/laravel_8_20251024/fruitcake/laravel-cors/src/HandleCors.php(38): Illuminate\\Pipeline\\Pipeline->Illuminate\\Pipeline\\{closure}()\n#34 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Pipeline/Pipeline.php(167): Fruitcake\\Cors\\HandleCors->handle()\n#35 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Http/Middleware/TrustProxies.php(39): Illuminate\\Pipeline\\Pipeline->Illuminate\\Pipeline\\{closure}()\n#36 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Pipeline/Pipeline.php(167): Illuminate\\Http\\Middleware\\TrustProxies->handle()\n#37 /var/sites/devmilanmobile.bizomdev.in/app/laravel/app/Http/Middleware/NormalizeUrlSlashes.php(41): Illuminate\\Pipeline\\Pipeline->Illuminate\\Pipeline\\{closure}()\n#38 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Pipeline/Pipeline.php(167): App\\Http\\Middleware\\NormalizeUrlSlashes->handle()\n#39 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Pipeline/Pipeline.php(103): Illuminate\\Pipeline\\Pipeline->Illuminate\\Pipeline\\{closure}()\n#40 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Foundation/Http/Kernel.php(142): Illuminate\\Pipeline\\Pipeline->then()\n#41 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Foundation/Http/Kernel.php(111): Illuminate\\Foundation\\Http\\Kernel->sendRequestThroughRouter()\n#42 /var/sites/devmilanmobile.bizomdev.in/app/laravel/public/index.php(51): Illuminate\\Foundation\\Http\\Kernel->handle()\n#43 /var/sites/devmilanmobile.bizomdev.in/app/webroot/index.php(14): require_once('/var/sites/devm...')\n#44 {main}",
  "exception_class": "ParseError",
  "category": "ParseError",
  "status_code": 500,
  "endpoint": "",
  "framework": "laravel",
  "source_file": "/var/sites/devmilanmobile.bizomdev.in/app/laravel/app/Http/Controllers/PaymentController.php",
  "first_seen_at": "2026-06-06T05:57:25Z"
},
# "laravel_array_merge_object_call_devext":{
#   "fingerprint": "f3a9e2c8b1d4f7a6c3e5b8d9f2a1c4e7b6d8f0a2c4e6b8d0f1a3c5e7b9d1f3a5c7",
#   "tenant": "devbbvietnam",
#   "error": "Undefined index: Appversion",
#   "stack_trace": "#0 [internal function]: Illuminate\\Foundation\\Bootstrap\\HandleExceptions->handleError()\n#1 /var/sites/devbbvietnam.bizomdev.in/app/laravel/app/Providers/TcpdfServiceProvider.php(42): call_user_func()\n#2 /var/sites/devbbvietnam.bizomdev.in/app/laravel/app/UserManagement/Repositories/UserRepository.php(16023): App\\Providers\\TcpdfServiceProvider->App\\Providers\\{closure}()\n#3 /var/sites/devbbvietnam.bizomdev.in/app/laravel/app/Http/Controllers/UserController.php(2095): App\\UserManagement\\Repositories\\UserRepository->updateappversionInternal()\n#4 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Routing/Controller.php(54): App\\Http\\Controllers\\UserController->updateappversion()\n#5 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Routing/ControllerDispatcher.php(45): Illuminate\\Routing\\Controller->callAction()\n#6 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Routing/Route.php(262): Illuminate\\Routing\\ControllerDispatcher->dispatch()\n#7 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Routing/Route.php(205): Illuminate\\Routing\\Route->runController()\n#8 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Routing/Router.php(721): Illuminate\\Routing\\Route->run()\n#9 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Pipeline/Pipeline.php(128): Illuminate\\Routing\\Router->Illuminate\\Routing\\{closure}()\n#10 /var/sites/devbbvietnam.bizomdev.in/app/laravel/app/Http/Middleware/ConvertJsonKeysToString.php(13): Illuminate\\Pipeline\\Pipeline->Illuminate\\Pipeline\\{closure}()\n#11 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Pipeline/Pipeline.php(167): App\\Http\\Middleware\\ConvertJsonKeysToString->handle()\n#12 /usr/share/vendor_bizom/laravel/laravel_8_20251024/inertiajs/inertia-laravel/src/Middleware.php(87): Illuminate\\Pipeline\\Pipeline->Illuminate\\Pipeline\\{closure}()\n#13 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Pipeline/Pipeline.php(167): Inertia\\Middleware->handle()\n#14 /var/sites/devbbvietnam.bizomdev.in/app/laravel/app/Http/Middleware/CheckPortalConfiguration.php(59): Illuminate\\Pipeline\\Pipeline->Illuminate\\Pipeline\\{closure}()\n#15 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Pipeline/Pipeline.php(167): App\\Http\\Middleware\\CheckPortalConfiguration->handle()\n#16 /var/sites/devbbvietnam.bizomdev.in/app/laravel/app/Http/Middleware/LogQueriesPerAction.php(17): Illuminate\\Pipeline\\Pipeline->Illuminate\\Pipeline\\{closure}()\n#17 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Pipeline/Pipeline.php(167): App\\Http\\Middleware\\LogQueriesPerAction->handle()\n#18 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Routing/Middleware/SubstituteBindings.php(50): Illuminate\\Pipeline\\Pipeline->Illuminate\\Pipeline\\{closure}()\n#19 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Pipeline/Pipeline.php(167): Illuminate\\Routing\\Middleware\\SubstituteBindings->handle()\n#20 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Auth/Middleware/Authenticate.php(44): Illuminate\\Pipeline\\Pipeline->Illuminate\\Pipeline\\{closure}()\n#21 /var/sites/devbbvietnam.bizomdev.in/app/laravel/app/Http/Middleware/Authenticate.php(30): Illuminate\\Auth\\Middleware\\Authenticate->handle()\n#22 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Pipeline/Pipeline.php(167): App\\Http\\Middleware\\Authenticate->handle()\n#23 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Foundation/Http/Middleware/VerifyCsrfToken.php(78): Illuminate\\Pipeline\\Pipeline->Illuminate\\Pipeline\\{closure}()\n#24 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Pipeline/Pipeline.php(167): Illuminate\\Foundation\\Http\\Middleware\\VerifyCsrfToken->handle()\n#25 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/View/Middleware/ShareErrorsFromSession.php(49): Illuminate\\Pipeline\\Pipeline->Illuminate\\Pipeline\\{closure}()\n#26 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Pipeline/Pipeline.php(167): Illuminate\\View\\Middleware\\ShareErrorsFromSession->handle()\n#27 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Session/Middleware/StartSession.php(121): Illuminate\\Pipeline\\Pipeline->Illuminate\\Pipeline\\{closure}()\n#28 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Session/Middleware/StartSession.php(64): Illuminate\\Session\\Middleware\\StartSession->handleStatefulRequest()\n#29 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Pipeline/Pipeline.php(167): Illuminate\\Session\\Middleware\\StartSession->handle()\n#30 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Cookie/Middleware/AddQueuedCookiesToResponse.php(37): Illuminate\\Pipeline\\Pipeline->Illuminate\\Pipeline\\{closure}()\n#31 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Pipeline/Pipeline.php(167): Illuminate\\Cookie\\Middleware\\AddQueuedCookiesToResponse->handle()\n#32 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Cookie/Middleware/EncryptCookies.php(67): Illuminate\\Pipeline\\Pipeline->Illuminate\\Pipeline\\{closure}()\n#33 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Pipeline/Pipeline.php(167): Illuminate\\Cookie\\Middleware\\EncryptCookies->handle()\n#34 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Pipeline/Pipeline.php(103): Illuminate\\Pipeline\\Pipeline->Illuminate\\Pipeline\\{closure}()\n#35 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Routing/Router.php(723): Illuminate\\Pipeline\\Pipeline->then()\n#36 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Routing/Router.php(698): Illuminate\\Routing\\Router->runRouteWithinStack()\n#37 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Routing/Router.php(662): Illuminate\\Routing\\Router->runRoute()\n#38 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Routing/Router.php(651): Illuminate\\Routing\\Router->dispatchToRoute()\n#39 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Foundation/Http/Kernel.php(167): Illuminate\\Routing\\Router->dispatch()\n#40 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Pipeline/Pipeline.php(128): Illuminate\\Foundation\\Http\\Kernel->Illuminate\\Foundation\\Http\\{closure}()\n#41 /var/sites/devbbvietnam.bizomdev.in/app/laravel/app/Http/Middleware/SetDatabaseConnection.php(86): Illuminate\\Pipeline\\Pipeline->Illuminate\\Pipeline\\{closure}()\n#42 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Pipeline/Pipeline.php(167): App\\Http\\Middleware\\SetDatabaseConnection->handle()\n#43 /var/sites/devbbvietnam.bizomdev.in/app/laravel/app/Http/Middleware/ClearOutputBuffer.php(23): Illuminate\\Pipeline\\Pipeline->Illuminate\\Pipeline\\{closure}()\n#44 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Pipeline/Pipeline.php(167): App\\Http\\Middleware\\ClearOutputBuffer->handle()\n#45 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Foundation/Http/Middleware/TransformsRequest.php(21): Illuminate\\Pipeline\\Pipeline->Illuminate\\Pipeline\\{closure}()\n#46 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Foundation/Http/Middleware/ConvertEmptyStringsToNull.php(31): Illuminate\\Foundation\\Http\\Middleware\\TransformsRequest->handle()\n#47 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Pipeline/Pipeline.php(167): Illuminate\\Foundation\\Http\\Middleware\\ConvertEmptyStringsToNull->handle()\n#48 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Foundation/Http/Middleware/TransformsRequest.php(21): Illuminate\\Pipeline\\Pipeline->Illuminate\\Pipeline\\{closure}()\n#49 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Foundation/Http/Middleware/TrimStrings.php(40): Illuminate\\Foundation\\Http\\Middleware\\TransformsRequest->handle()\n#50 /var/sites/devbbvietnam.bizomdev.in/app/laravel/app/Http/Middleware/TrimStrings.php(26): Illuminate\\Foundation\\Http\\Middleware\\TrimStrings->handle()\n#51 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Pipeline/Pipeline.php(167): App\\Http\\Middleware\\TrimStrings->handle()\n#52 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Foundation/Http/Middleware/ValidatePostSize.php(27): Illuminate\\Pipeline\\Pipeline->Illuminate\\Pipeline\\{closure}()\n#53 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Pipeline/Pipeline.php(167): Illuminate\\Foundation\\Http\\Middleware\\ValidatePostSize->handle()\n#54 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Foundation/Http/Middleware/PreventRequestsDuringMaintenance.php(86): Illuminate\\Pipeline\\Pipeline->Illuminate\\Pipeline\\{closure}()\n#55 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Pipeline/Pipeline.php(167): Illuminate\\Foundation\\Http\\Middleware\\PreventRequestsDuringMaintenance->handle()\n#56 /usr/share/vendor_bizom/laravel/laravel_8_20251024/fruitcake/laravel-cors/src/HandleCors.php(38): Illuminate\\Pipeline\\Pipeline->Illuminate\\Pipeline\\{closure}()\n#57 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Pipeline/Pipeline.php(167): Fruitcake\\Cors\\HandleCors->handle()\n#58 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Http/Middleware/TrustProxies.php(39): Illuminate\\Pipeline\\Pipeline->Illuminate\\Pipeline\\{closure}()\n#59 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Pipeline/Pipeline.php(167): Illuminate\\Http\\Middleware\\TrustProxies->handle()\n#60 /var/sites/devbbvietnam.bizomdev.in/app/laravel/app/Http/Middleware/NormalizeUrlSlashes.php(41): Illuminate\\Pipeline\\Pipeline->Illuminate\\Pipeline\\{closure}()\n#61 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Pipeline/Pipeline.php(167): App\\Http\\Middleware\\NormalizeUrlSlashes->handle()\n#62 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Pipeline/Pipeline.php(103): Illuminate\\Pipeline\\Pipeline->Illuminate\\Pipeline\\{closure}()\n#63 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Foundation/Http/Kernel.php(142): Illuminate\\Pipeline\\Pipeline->then()\n#64 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/Foundation/Http/Kernel.php(111): Illuminate\\Foundation\\Http\\Kernel->sendRequestThroughRouter()\n#65 /var/sites/devbbvietnam.bizomdev.in/app/laravel/public/index.php(51): Illuminate\\Foundation\\Http\\Kernel->handle()\n#66 /var/sites/devbbvietnam.bizomdev.in/app/webroot/index.php(14): require_once('/var/sites/devb...')\n#67 {main}",
#   "exception_class": "ErrorException",
#   "category": "Undefined index",
#   "status_code": 500,
#   "endpoint": "/user/updateappversion",
#   "framework": "laravel",
#   "source_file": "/var/sites/devbbvietnam.bizomdev.in/app/laravel/app/UserManagement/Repositories/UserRepository.php",
#   "first_seen_at": "2026-06-03T10:34:54Z"
# },

# "laravel_trying_to_access_array_offset_on_null": {
#     "group": "novel",
#     "fingerprint": "abc123",
#     "tenant": "godrejindo.bizom.in",
#     "error": "Trying to access array offset on value of type null",
#     "exception_class": "ErrorException",
#     "category": "Trying to access array offset",
#     "status_code": 500,
#     "endpoint": "/inventory/transferHistory",
#     "framework": "laravel",
#     "source_file": "/var/sites/godrejindo.bizom.in/app/laravel/app/TransactionManagement/Repositories/InventoryRepository.php",
#     "first_seen_at": "2026-06-06T10:00:00Z",
#     "stack_trace": (
#         "#0 /var/sites/godrejindo.bizom.in/app/laravel/app/TransactionManagement/"
#         "Repositories/InventoryRepository.php(11236): "
#         "Illuminate\\Foundation\\Bootstrap\\HandleExceptions->handleError()\n"
#         "#1 /var/sites/godrejindo.bizom.in/app/laravel/app/Http/Controllers/"
#         "InventoryController.php(894): "
#         "App\\TransactionManagement\\Repositories\\InventoryRepository"
#         "->transferHistoryInternal()\n"
#         "#2 /usr/share/vendor_bizom/laravel/laravel_8_20251024/"
#         "laravel/framework/src/Illuminate/Routing/Controller.php(54): "
#         "App\\Http\\Controllers\\InventoryController->transferHistory()\n"
#         "#3 /usr/share/vendor_bizom/laravel/laravel_8_20251024/"
#         "laravel/framework/src/Illuminate/Routing/ControllerDispatcher.php(45): "
#         "Illuminate\\Routing\\Controller->callAction()\n"
#         "#4 /usr/share/vendor_bizom/laravel/laravel_8_20251024/"
#         "laravel/framework/src/Illuminate/Routing/Route.php(262): "
#         "Illuminate\\Routing\\ControllerDispatcher->dispatch()\n"
#         "#5 /usr/share/vendor_bizom/laravel/laravel_8_20251024/"
#         "laravel/framework/src/Illuminate/Routing/Route.php(205): "
#         "Illuminate\\Routing\\Route->runController()\n"
#         "#6 /usr/share/vendor_bizom/laravel/laravel_8_20251024/"
#         "laravel/framework/src/Illuminate/Routing/Router.php(721): "
#         "Illuminate\\Routing\\Route->run()\n"
#         "#57 /var/sites/godrejindo.bizom.in/app/laravel/public/index.php(51): "
#         "Illuminate\\Foundation\\Http\\Kernel->handle()\n"
#         "#58 /var/sites/godrejindo.bizom.in/app/webroot/index.php(14): "
#         "require_once('/var/sites/godr...')\n"
#         "#59 {main}"
#     ),
# },

# "laravel_undefined_index_desingation_name": {
#     "group": "novel",
#     "domain": "nagamills.bizom.in",
#     "log": (
#         "Undefined index: desingation_name "
#         '{"userId":8,"exception":"[object] '
#         "(ErrorException(code: 0): Undefined index: desingation_name "
#         "at /var/sites/nagamills.bizom.in/app/laravel/app/UserManagement/"
#         "Repositories/AttendanceRepository.php:2564)\n"
#         "[stacktrace]\n"
#         "#0 /var/sites/nagamills.bizom.in/app/laravel/app/UserManagement/"
#         "Repositories/AttendanceRepository.php(2564): "
#         "Illuminate\\Foundation\\Bootstrap\\HandleExceptions->handleError()\n"
#         "#1 /var/sites/nagamills.bizom.in/app/laravel/app/Http/Controllers/"
#         "AttendanceController.php(213): "
#         "App\\UserManagement\\Repositories\\AttendanceRepository"
#         "->attendanceReportDownloadInternal()\n"
#         "#2 /usr/share/vendor_bizom/laravel/laravel_8_20251024/"
#         "laravel/framework/src/Illuminate/Routing/Controller.php(54): "
#         "App\\Http\\Controllers\\AttendanceController"
#         "->attendance_report_download()\n"
#         "#3 /usr/share/vendor_bizom/laravel/laravel_8_20251024/"
#         "laravel/framework/src/Illuminate/Routing/ControllerDispatcher.php(45): "
#         "Illuminate\\Routing\\Controller->callAction()\n"
#         "#4 /usr/share/vendor_bizom/laravel/laravel_8_20251024/"
#         "laravel/framework/src/Illuminate/Routing/Route.php(262): "
#         "Illuminate\\Routing\\ControllerDispatcher->dispatch()\n"
#         "#5 /usr/share/vendor_bizom/laravel/laravel_8_20251024/"
#         "laravel/framework/src/Illuminate/Routing/Route.php(205): "
#         "Illuminate\\Routing\\Route->runController()\n"
#         "#6 /usr/share/vendor_bizom/laravel/laravel_8_20251024/"
#         "laravel/framework/src/Illuminate/Routing/Router.php(721): "
#         "Illuminate\\Routing\\Route->run()\n"
#         "#7 /usr/share/vendor_bizom/laravel/laravel_8_20251024/"
#         "laravel/framework/src/Illuminate/Pipeline/Pipeline.php(128): "
#         "Illuminate\\Routing\\Router->Illuminate\\Routing\\{closure}()\n"
#         "#8 ...\n"
#         "#61 /var/sites/nagamills.bizom.in/app/laravel/public/index.php(51): "
#         "Illuminate\\Foundation\\Http\\Kernel->handle()\n"
#         "#62 /var/sites/nagamills.bizom.in/app/webroot/index.php(14): "
#         "require_once('/var/sites/naga...')\n"
#         "#63 {main}"
#         '"}'
#     ),
# },

    # "laravel_sql_fordate_like_known": {
    #     "group": "known",
    #     "note": "pureplaydms.bizom.in — same SQLSTATE error, different domain (should be KNOWN)",
    #     "log": (
    #         "SQLSTATE[42S22]: Column not found: 1054 Unknown column 'Payment.fordate LIKE' in "
    #         "'where clause' {\"userId\":697,\"exception\":\"[object] (Illuminate\\\\Database\\\\"
    #         "QueryException(code: 42S22): SQLSTATE[42S22]: Column not found: 1054 Unknown column "
    #         "'Payment.fordate LIKE' in 'where clause' at /usr/share/vendor_bizom/laravel/"
    #         "laravel_8_20251024/laravel/framework/src/Illuminate/Database/Connection.php:712)\n"
    #         "[stacktrace]\n"
    #         "#0 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/"
    #         "Database/Connection.php(672): Illuminate\\\\Database\\\\Connection->runQueryCallback()\n"
    #         "#12 /var/sites/pureplaydms.bizom.in/app/laravel/app/TransactionManagement/Repositories/"
    #         "PaymentRepository.php(14225): Yajra\\\\DataTables\\\\QueryDataTable->make()\n"
    #         "#13 /var/sites/pureplaydms.bizom.in/app/laravel/app/Http/Controllers/"
    #         "PaymentController.php(715): App\\\\TransactionManagement\\\\Repositories\\\\"
    #         "PaymentRepository->getInvoicesForReturnInternal()\"}"
    #     ),
    # },

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
        # Strip runner-only keys before passing to process_event
        payload = {k: v for k, v in spec.items() if k not in ("group", "note")}
        r = o.process_event(payload)
        print(f"  status={r.status}  similarity={r.similarity}  pr={r.pr_url or '-'}", flush=True)
        if r.detail:
            print(f"  detail={r.detail[:200]}", flush=True)


if __name__ == "__main__":
    main()
