#!/usr/bin/env bash

set -uo pipefail

YEARS=(2025 2026)

RATE_URLS=(
  "https://www.skatteetaten.no/en/Rates/Minimum-standard-deduction/"
  "https://www.skatteetaten.no/en/rates/personal-allowance/"
  "https://www.skatteetaten.no/en/Rates/General-income/"
  "https://www.skatteetaten.no/en/Rates/bracket-tax/"
  "https://www.skatteetaten.no/en/rates/national-insurance-contributions/"
  "https://www.skatteetaten.no/en/Rates/Wealth-tax/"
  "https://www.skatteetaten.no/en/rates/tax-value-of-housing/"
  "https://www.skatteetaten.no/en/Rates/Deduction-for-travel-between-home-and-work/"
  "https://www.skatteetaten.no/en/Rates/Deduction-for-young-peoples-housing-savings-BSU/"
  "https://www.skatteetaten.no/en/rates/deduction-for-trade-union-fees/"
  "https://www.skatteetaten.no/en/rates/tax-allowance-for-pension-income/"
  "https://www.skatteetaten.no/en/rates/factor-for-upward-adjustment-of-gainloss-or-dividend-on-shares/"
  "https://www.skatteetaten.no/en/rates/home-office-standard-deduction/"
  "https://www.skatteetaten.no/en/Rates/board-and-lodging---deduction-rates/"
  "https://www.skatteetaten.no/en/Rates/Interest-rates-on-refunds-underpaid-tax-and-outstanding-tax/"
  "https://www.skatteetaten.no/en/Rates/Gifts-to-voluntary-organisations/"
  "https://www.skatteetaten.no/en/Rates/Maximum-effective-marginal-tax-rates/"
)

GUIDANCE_URLS=(
  "https://www.skatteetaten.no/en/person/taxes/get-the-taxes-right/family-and-health/children/child-care-deduction/"
  "https://www.skatteetaten.no/en/person/taxes/get-the-taxes-right/employment-benefits-and-pensions/deduction-for-trade-union-fees/"
  "https://www.skatteetaten.no/en/person/taxes/get-the-taxes-right/bank-and-loans/bsu---young-peoples-housing-savings/"
  "https://www.skatteetaten.no/en/person/taxes/get-the-taxes-right/employment-benefits-and-pensions/travel-home-work/travel-deduction/"
  "https://www.skatteetaten.no/en/person/taxes/get-the-taxes-right/property-and-belongings/houses-property-and-plots-of-land/tax-value/taxable-value-of-residential-properties/"
  "https://www.skatteetaten.no/en/person/taxes/get-the-taxes-right/employment-benefits-and-pensions/if-your-employer-pays/working-from-home-and-tax/"
  "https://www.skatteetaten.no/en/person/taxes/get-the-taxes-right/employment-benefits-and-pensions/pension-and-disability-benefit/a-new-scheme-concerning-tax-favourable-individual-pension-saving/"
  "https://www.skatteetaten.no/en/person/taxes/get-the-taxes-right/employment-benefits-and-pensions/pension-and-disability-benefit/tax-rules-for-pensioners/rates-and-thresholds/"
  "https://www.skatteetaten.no/en/person/taxes/get-the-taxes-right/gift-and-inheritance/gift-to-organisation/"
  "https://www.skatteetaten.no/en/person/taxes/get-the-taxes-right/abroad/income-and-wealth-abroad/income-and-wealth-abroad/"
)

RUN_ID="$(date +%Y%m%d_%H%M%S)"
LOG_DIR="data/manifests/crawl_runs"
LOG_FILE="${LOG_DIR}/rates_v1_${RUN_ID}.log"
FAILED_FILE="${LOG_DIR}/rates_v1_${RUN_ID}_failed.txt"

mkdir -p "$LOG_DIR"

success=0
failed=0

crawl_one() {
  local url="$1"
  local label="$2"

  echo
  echo "================================================================"
  echo "$label"
  echo "$url"
  echo "================================================================"

  if uv run taxguide crawl \
      "$url" \
      --max-pages 1 \
      --no-follow \
      2>&1 | tee -a "$LOG_FILE"
  then
    success=$((success + 1))
  else
    failed=$((failed + 1))
    echo "$url" >> "$FAILED_FILE"
    echo "FAILED: $url" | tee -a "$LOG_FILE"
  fi

  # Be polite to the source and avoid sending requests back-to-back.
  sleep 0.5
}

echo "TaxGuide Norway rates crawl v1" | tee "$LOG_FILE"
echo "Run: $RUN_ID" | tee -a "$LOG_FILE"
echo "Years: ${YEARS[*]}" | tee -a "$LOG_FILE"

echo
echo "=== YEAR-SPECIFIC RATE PAGES ==="

for base in "${RATE_URLS[@]}"; do
  for year in "${YEARS[@]}"; do
    crawl_one "${base}?year=${year}" "RATE year=${year}"
  done
done

echo
echo "=== GUIDANCE PAGES ==="

for url in "${GUIDANCE_URLS[@]}"; do
  crawl_one "$url" "GUIDANCE"
done

echo
echo "================================================================"
echo "CRAWL COMPLETE"
echo "Success: $success"
echo "Failed:  $failed"
echo "Log:     $LOG_FILE"

if (( failed > 0 )); then
  echo "Failures: $FAILED_FILE"
  exit 1
fi