"""Archived preprocessing entry point (illustrative, not executable here)."""

def build_reference(expression, membership):
    fit_ids = membership.loc[membership["included_in_reference_fit"], "sample_id"]
    return expression.loc[fit_ids].mean(axis=0), expression.loc[fit_ids].std(axis=0)

def transform(expression, reference_mean, reference_std):
    return (expression - reference_mean) / reference_std
