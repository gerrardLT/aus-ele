from urllib.parse import urlencode


def parse_discovery_document(document: dict) -> dict:
    required = ["issuer", "authorization_endpoint", "token_endpoint", "jwks_uri"]
    missing = [key for key in required if not document.get(key)]
    if missing:
        raise ValueError(f"Missing discovery keys: {', '.join(missing)}")
    return {
        "issuer": document["issuer"],
        "authorization_endpoint": document["authorization_endpoint"],
        "token_endpoint": document["token_endpoint"],
        "userinfo_endpoint": document.get("userinfo_endpoint"),
        "jwks_uri": document["jwks_uri"],
    }


def build_authorization_redirect(*, provider: dict, discovery: dict, redirect_uri: str, state: str, nonce: str) -> str:
    query = urlencode(
        {
            "client_id": provider["client_id"],
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "scope": " ".join(provider.get("scopes_json") or ["openid", "email", "profile"]),
            "state": state,
            "nonce": nonce,
        }
    )
    return f"{discovery['authorization_endpoint']}?{query}"
