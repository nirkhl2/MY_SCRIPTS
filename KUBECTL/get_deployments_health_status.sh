NS="${NS:-default}"
BASE_URL="${BASE_URL:?}"
HEALTH_PATH="${HEALTH_PATH:-/actuator/health}"
SELECTOR="${SELECTOR:-}"
TOKEN="${TOKEN:-}"
TIMEOUT="${TIMEOUT:-30}"

args=(-n "$NS")
[[ -n "$SELECTOR" ]] && args+=( -l "$SELECTOR" )

deps=$(kubectl get deploy "${args[@]}" -o jsonpath='{range .items[*]}{.metadata.name}{"\n"}{end}')

while IFS= read -r dep; do
  [[ -z "$dep" ]] && continue
  echo "Checking $dep..."
  url="${BASE_URL}/${dep}${HEALTH_PATH}"

  authHeader=()
  [[ -n "$TOKEN" ]] && authHeader=(-H "Authorization: Bearer $TOKEN")

  response=$(curl -sS --max-time "$TIMEOUT" -H "Accept: application/json" "${authHeader[@]}" "$url" || true)

  [[ -z "$response" ]] && echo "No response (timeout/error/empty)" || echo "$response"
  echo
done <<< "$deps"