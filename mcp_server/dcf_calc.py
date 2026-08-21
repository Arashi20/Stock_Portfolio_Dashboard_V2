"""DCF valuation math for the MCP server.

KEEP IN SYNC WITH ../dcf/dcf_default.py -- this is a verbatim copy of
dcf_valuation_advanced(). The MCP server is deployed as its own Railway service
rooted at mcp_server/, so it can't import the main app's `dcf` package; copying
the function is the same trade-off already made for sanitize_html() in db.py.

Both services must produce identical intrinsic values for identical inputs, so
if the model in ../dcf/dcf_default.py changes, mirror the change here.
"""


def dcf_valuation_advanced(
    initial_fcf,
    growth_rate_1_5,
    growth_rate_6_10,
    discount_rate,
    terminal_growth_rate,
    shares_outstanding,
    share_change_rate=0.0,  # Positive for dilution, Negative for buybacks, 0 for no change
):
    """
    Calculates Intrinsic Value per Share accounting for changing share counts.

    Parameters:
    - share_change_rate: Annual % change in share count (e.g., 2.0 for 2% dilution, -2.0 for 2% buyback, 0 for no change)
    """

    # --- 1. Input Conversion & Validation ---
    growth_rate_1_5 /= 100
    growth_rate_6_10 /= 100
    discount_rate /= 100
    terminal_growth_rate /= 100
    share_change_rate /= 100

    if discount_rate <= terminal_growth_rate:
        raise ValueError("Discount rate must be greater than terminal growth rate.")

    if shares_outstanding <= 0:
        raise ValueError("Shares outstanding must be a positive number.")

    # --- 2. Projection Loop (Years 1-10) ---
    discounted_fcf_per_share_values = []

    current_fcf = initial_fcf
    current_shares = shares_outstanding

    for year in range(1, 11):
        # A. Grow the Total Free Cash Flow
        if year <= 5:
            current_fcf = current_fcf * (1 + growth_rate_1_5)
        else:
            current_fcf = current_fcf * (1 + growth_rate_6_10)

        # B. Adjust Share Count (Compound the dilution/buyback)
        current_shares = current_shares * (1 + share_change_rate)

        # C. Calculate FCF Per Share for this specific year
        fcf_per_share = current_fcf / current_shares

        # D. Discount this year's FCF/Share to Present Value
        pv_fcf_per_share = fcf_per_share / ((1 + discount_rate) ** year)
        discounted_fcf_per_share_values.append(pv_fcf_per_share)

    # --- 3. Terminal Value Calculation ---
    total_terminal_value = (current_fcf * (1 + terminal_growth_rate)) / (discount_rate - terminal_growth_rate)

    terminal_value_per_share = total_terminal_value / current_shares

    discounted_terminal_value_per_share = terminal_value_per_share / ((1 + discount_rate) ** 10)

    # --- 4. Final Summation ---
    intrinsic_value_per_share = sum(discounted_fcf_per_share_values) + discounted_terminal_value_per_share

    return intrinsic_value_per_share
