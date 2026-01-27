# Simple 2-stage DCF calculator with Share Dilution/Buyback logic
def dcf_valuation_advanced(
    initial_fcf, 
    growth_rate_1_5, 
    growth_rate_6_10, 
    discount_rate, 
    terminal_growth_rate, 
    shares_outstanding, 
    share_change_rate=0.0  # Positive for dilution, Negative for buybacks, 0 for no change
):
    """
    Calculates Intrinsic Value per Share accounting for changing share counts.
    
    Parameters:
    - share_change_rate: Annual % change in share count (e.g., 2.0 for 2% dilution, -2.0 for 2% buyback, 0 for no change)
    """

    # --- 1. Input Conversion & Validation ---
    # Convert percentage inputs to decimals
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
    
    # Trackers for the loop
    current_fcf = initial_fcf
    current_shares = shares_outstanding

    # print(f"{'Year':<5} | {'Total FCF':<15} | {'Shares':<15} | {'FCF/Share':<10}")
    # print("-" * 55)

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
    # We calculate terminal value based on Year 10 totals
    # Formula: (FCF_Year_10 * (1 + g)) / (r - g)
    total_terminal_value = (current_fcf * (1 + terminal_growth_rate)) / (discount_rate - terminal_growth_rate)
    
    # IMPORTANT: We must divide the Total Terminal Value by the Year 10 Share Count
    # This assumes the dilution stops or stabilizes, or simply that the claim on the 
    # terminal value is split among the shares that exist in year 10.
    terminal_value_per_share = total_terminal_value / current_shares
    
    # Discount the Terminal Value Per Share back to today
    discounted_terminal_value_per_share = terminal_value_per_share / ((1 + discount_rate) ** 10)

    # --- 4. Final Summation ---
    intrinsic_value_per_share = sum(discounted_fcf_per_share_values) + discounted_terminal_value_per_share
    
    return intrinsic_value_per_share

# Uncomment the following lines to run an example calculation:

# --- Usage Example ---
# Scenario: 
# $100M FCF, Growing 15% then 10%. 
# 10% Discount Rate. 3% Terminal Growth.
# 50M Shares.
# 2% Annual Dilution (Share count increases by 2% every year)

# price_target = dcf_valuation_advanced(
#     initial_fcf=100_000_000, 
#     growth_rate_1_5=15, 
#     growth_rate_6_10=10, 
#     discount_rate=10, 
#     terminal_growth_rate=3, 
#     shares_outstanding=50_000_000,
#     share_change_rate=2.0 
# )

# print(f"\nIntrinsic Value per Share: ${price_target:.2f}")