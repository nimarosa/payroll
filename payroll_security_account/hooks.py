"""Propose an existing salary journal as the initial value of
`res.company.payroll_salary_journal_id`, on install. Never creates a journal:
a company with none, or with more than one candidate, is left for someone to
decide by hand in the Payroll settings."""

import logging

_logger = logging.getLogger(__name__)


def _candidate_names(env):
    """The names a salary journal is likely to carry, in English and in every
    installed language this module is translated to. Matched
    case-insensitively against the whole (stripped) journal name -- not a
    substring match, so "Salaries and wages" is deliberately NOT proposed on
    its own: ambiguity is left for a human, this never guesses."""
    names = set()
    langs = {code for code, _name in env["res.lang"].get_installed()} | {"en_US"}
    for lang in langs:
        lang_env = env(context=dict(env.context, lang=lang))
        names |= {lang_env._("Salaries"), lang_env._("Payroll")}
    return {name.strip().lower() for name in names}


def propose_salary_journal(env):
    names = _candidate_names(env)
    companies = env["res.company"].search([("payroll_salary_journal_id", "=", False)])
    for company in companies:
        journals = env["account.journal"].search(
            [("type", "=", "general"), ("company_id", "=", company.id)]
        )
        candidates = journals.filtered(
            lambda journal: (journal.name or "").strip().lower() in names
        )
        if len(candidates) == 1:
            company.payroll_salary_journal_id = candidates.id
            _logger.info(
                "payroll_security_account: proposed %r as the salary journal of %s",
                candidates.name,
                company.display_name,
            )


def post_init_hook(env):
    propose_salary_journal(env)
