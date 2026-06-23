from datetime import date as DateType

import plaid
from plaid.api import plaid_api
from plaid.model.accounts_get_request import AccountsGetRequest
from plaid.model.country_code import CountryCode
from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest
from plaid.model.link_token_create_request import LinkTokenCreateRequest
from plaid.model.link_token_create_request_user import LinkTokenCreateRequestUser
from plaid.model.products import Products
from plaid.model.transactions_get_request import TransactionsGetRequest
from plaid.model.transactions_get_request_options import TransactionsGetRequestOptions

_ENV_MAP = {
    "sandbox": plaid.Environment.Sandbox,
    "production": plaid.Environment.Production,
}


def make_plaid_client(settings) -> plaid_api.PlaidApi:
    if settings.plaid_env not in _ENV_MAP:
        raise ValueError(f"Invalid PLAID_ENV '{settings.plaid_env}'. Must be one of: {list(_ENV_MAP)}")
    configuration = plaid.Configuration(
        host=_ENV_MAP[settings.plaid_env],
        api_key={
            "clientId": settings.plaid_client_id,
            "secret": settings.plaid_secret,
        },
    )
    return plaid_api.PlaidApi(plaid.ApiClient(configuration))


def create_link_token(client: plaid_api.PlaidApi) -> str:
    request = LinkTokenCreateRequest(
        products=[Products("transactions")],
        client_name="Ledger Agent",
        country_codes=[CountryCode("US")],
        language="en",
        user=LinkTokenCreateRequestUser(client_user_id="local-user"),
    )
    response = client.link_token_create(request)
    return response["link_token"]


def exchange_public_token(client: plaid_api.PlaidApi, public_token: str) -> tuple[str, str]:
    response = client.item_public_token_exchange(
        ItemPublicTokenExchangeRequest(public_token=public_token)
    )
    return response["access_token"], response["item_id"]


def fetch_transactions(
    client: plaid_api.PlaidApi,
    access_token: str,
    start_date: DateType,
    end_date: DateType,
) -> list[dict]:
    all_transactions = []
    offset = 0
    while True:
        request = TransactionsGetRequest(
            access_token=access_token,
            start_date=start_date,
            end_date=end_date,
            options=TransactionsGetRequestOptions(count=500, offset=offset),
        )
        response = client.transactions_get(request)
        batch = response["transactions"]
        if not batch:
            break
        all_transactions.extend(batch)
        if len(all_transactions) >= response["total_transactions"]:
            break
        offset += len(batch)
    return [
        {
            "plaid_transaction_id": txn["transaction_id"],
            "description": txn["name"],
            "merchant_name": txn.get("merchant_name"),
            "amount": txn["amount"],
            "date": txn["date"],
        }
        for txn in all_transactions
    ]


def fetch_accounts(client: plaid_api.PlaidApi, access_token: str) -> list[dict]:
    response = client.accounts_get(AccountsGetRequest(access_token=access_token))
    return [
        {
            "plaid_account_id": acct["account_id"],
            "name": acct["name"],
            "type": str(acct["type"]),
        }
        for acct in response["accounts"]
    ]
