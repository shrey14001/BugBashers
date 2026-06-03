"""
tests/test_parsers.py
Unit tests for the Laravel and CakePHP 2 log parsers.
"""

import pytest
from autofix.parsers.laravel  import parse as parse_laravel
from autofix.parsers.cakephp2 import parse as parse_cakephp2


# ── Sample log fixtures ───────────────────────────────────────────────────────

LARAVEL_LOG = (
    'Function name must be a string {"userId":177,"exception":"[object] (Error(code: 0): '
    'Function name must be a string at /var/sites/demo.bizom.in/app/laravel/app/'
    'CompanyManagement/Repositories/OutletRepository.php:14252)\n'
    '[stacktrace]\n'
    '#0 /var/sites/demo.bizom.in/app/laravel/app/CompanyManagement/Repositories/'
    'OutletRepository.php(14215): App\\CompanyManagement\\Repositories\\OutletRepository->getExtraParams()\n'
    '#1 /var/sites/demo.bizom.in/app/laravel/app/Http/Controllers/'
    'OutletController.php(1914): App\\Http\\Controllers\\OutletController->getPendingInvoicesMultiDistributor()"}'
)

CAKEPHP_LOG = (
    "2024-01-15 10:23:45 Error: Fatal error: "
    "Call to undefined method Order::findByStatus() "
    "in /var/sites/demo.bizom.in/app/Model/Order.php on line 77\n"
    "Stack trace:\n"
    "#0 /var/sites/demo.bizom.in/app/Controller/OrdersController.php(120): Order->findByStatus()\n"
    "#1 /var/sites/demo.bizom.in/app/Controller/AppController.php(44): OrdersController->index()"
)


# ── Laravel parser tests ──────────────────────────────────────────────────────

class TestLaravelParser:
    def test_returns_parsed_error(self):
        result = parse_laravel(LARAVEL_LOG)
        assert result is not None

    def test_framework_is_laravel(self):
        result = parse_laravel(LARAVEL_LOG)
        assert result.framework == "laravel"

    def test_has_stack_frames(self):
        result = parse_laravel(LARAVEL_LOG)
        assert len(result.stack_frames) > 0

    def test_top_frame_is_app_file(self):
        result = parse_laravel(LARAVEL_LOG)
        top = result.top_frame()
        assert top is not None
        assert "/vendor/" not in top.file

    def test_embedding_text_not_empty(self):
        result = parse_laravel(LARAVEL_LOG)
        assert result.embedding_text().strip() != ""

    def test_domain_is_propagated(self):
        result = parse_laravel(LARAVEL_LOG, domain="demo.bizom.in")
        assert result.domain == "demo.bizom.in"

    def test_returns_none_for_unrecognised_log(self):
        assert parse_laravel("this is not a log line") is None


# ── CakePHP 2 parser tests ────────────────────────────────────────────────────

class TestCakePHP2Parser:
    def test_returns_parsed_error(self):
        result = parse_cakephp2(CAKEPHP_LOG)
        assert result is not None

    def test_framework_is_cakephp2(self):
        result = parse_cakephp2(CAKEPHP_LOG)
        assert result.framework == "cakephp2"

    def test_level_is_critical_for_fatal(self):
        result = parse_cakephp2(CAKEPHP_LOG)
        assert result.level == "CRITICAL"

    def test_has_stack_frames(self):
        result = parse_cakephp2(CAKEPHP_LOG)
        assert len(result.stack_frames) > 0

    def test_error_message_stripped(self):
        result = parse_cakephp2(CAKEPHP_LOG)
        assert result.error_message != ""

    def test_returns_none_for_unrecognised_log(self):
        assert parse_cakephp2("random text without timestamp") is None
