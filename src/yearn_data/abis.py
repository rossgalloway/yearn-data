"""Minimal ABIs used by the indexer."""

ERC20_ABI = [
    {
        "type": "function",
        "name": "decimals",
        "inputs": [],
        "outputs": [{"type": "uint8", "name": ""}],
        "stateMutability": "view",
    },
    {
        "type": "function",
        "name": "symbol",
        "inputs": [],
        "outputs": [{"type": "string", "name": ""}],
        "stateMutability": "view",
    },
    {
        "type": "function",
        "name": "name",
        "inputs": [],
        "outputs": [{"type": "string", "name": ""}],
        "stateMutability": "view",
    },
]

ROLE_MANAGER_ABI = [
    {
        "type": "function",
        "name": "getAllVaults",
        "inputs": [],
        "outputs": [{"type": "address[]", "name": ""}],
        "stateMutability": "view",
    }
]

V3_VAULT_FACTORY_NEW_VAULT_EVENT = {
    "anonymous": False,
    "type": "event",
    "name": "NewVault",
    "inputs": [
        {"indexed": True, "type": "address", "name": "vault_address"},
        {"indexed": True, "type": "address", "name": "asset"},
    ],
}

V2_REGISTRY_ABI = [
    {
        "anonymous": False,
        "type": "event",
        "name": "NewVault",
        "inputs": [
            {"indexed": True, "type": "address", "name": "token"},
            {"indexed": True, "type": "uint256", "name": "vault_id"},
            {"indexed": False, "type": "address", "name": "vault"},
            {"indexed": False, "type": "string", "name": "api_version"},
        ],
    },
    {
        "anonymous": False,
        "type": "event",
        "name": "NewVault",
        "inputs": [
            {"indexed": True, "type": "address", "name": "token"},
            {"indexed": True, "type": "uint256", "name": "vaultId"},
            {"indexed": False, "type": "uint256", "name": "vaultType"},
            {"indexed": False, "type": "address", "name": "vault"},
            {"indexed": False, "type": "string", "name": "apiVersion"},
        ],
    },
    {
        "type": "function",
        "name": "numTokens",
        "inputs": [],
        "outputs": [{"type": "uint256", "name": ""}],
        "stateMutability": "view",
    },
    {
        "type": "function",
        "name": "tokens",
        "inputs": [{"type": "uint256", "name": ""}],
        "outputs": [{"type": "address", "name": ""}],
        "stateMutability": "view",
    },
    {
        "type": "function",
        "name": "numVaults",
        "inputs": [{"type": "address", "name": ""}],
        "outputs": [{"type": "uint256", "name": ""}],
        "stateMutability": "view",
    },
    {
        "type": "function",
        "name": "vaults",
        "inputs": [{"type": "address", "name": ""}, {"type": "uint256", "name": ""}],
        "outputs": [{"type": "address", "name": ""}],
        "stateMutability": "view",
    },
]

VAULT_METADATA_ABI = [
    {
        "type": "function",
        "name": "asset",
        "inputs": [],
        "outputs": [{"type": "address", "name": ""}],
        "stateMutability": "view",
    },
    {
        "type": "function",
        "name": "token",
        "inputs": [],
        "outputs": [{"type": "address", "name": ""}],
        "stateMutability": "view",
    },
    {
        "type": "function",
        "name": "apiVersion",
        "inputs": [],
        "outputs": [{"type": "string", "name": ""}],
        "stateMutability": "view",
    },
    *ERC20_ABI,
]

VAULT_SHARE_PRICE_ABI = [
    {
        "type": "function",
        "name": "pricePerShare",
        "inputs": [],
        "outputs": [{"type": "uint256", "name": ""}],
        "stateMutability": "view",
    },
    {
        "type": "function",
        "name": "getPricePerFullShare",
        "inputs": [],
        "outputs": [{"type": "uint256", "name": ""}],
        "stateMutability": "view",
    },
    {
        "type": "function",
        "name": "decimals",
        "inputs": [],
        "outputs": [{"type": "uint8", "name": ""}],
        "stateMutability": "view",
    },
]

V3_STRATEGY_REPORTED_EVENT = {
    "anonymous": False,
    "type": "event",
    "name": "StrategyReported",
    "inputs": [
        {"indexed": True, "type": "address", "name": "strategy"},
        {"indexed": False, "type": "uint256", "name": "gain"},
        {"indexed": False, "type": "uint256", "name": "loss"},
        {"indexed": False, "type": "uint256", "name": "current_debt"},
        {"indexed": False, "type": "uint256", "name": "protocol_fees"},
        {"indexed": False, "type": "uint256", "name": "total_fees"},
        {"indexed": False, "type": "uint256", "name": "total_refunds"},
    ],
}

V2_STRATEGY_REPORTED_EVENTS = [
    {
        "anonymous": False,
        "type": "event",
        "name": "StrategyReported",
        "inputs": [
            {"indexed": True, "type": "address", "name": "strategy"},
            {"indexed": False, "type": "uint256", "name": "gain"},
            {"indexed": False, "type": "uint256", "name": "loss"},
            {"indexed": False, "type": "uint256", "name": "debtPaid"},
            {"indexed": False, "type": "uint256", "name": "totalGain"},
            {"indexed": False, "type": "uint256", "name": "totalLoss"},
            {"indexed": False, "type": "uint256", "name": "totalDebt"},
            {"indexed": False, "type": "uint256", "name": "debtAdded"},
            {"indexed": False, "type": "uint256", "name": "debtRatio"},
        ],
    },
    {
        "anonymous": False,
        "type": "event",
        "name": "StrategyReported",
        "inputs": [
            {"indexed": True, "type": "address", "name": "strategy"},
            {"indexed": False, "type": "uint256", "name": "gain"},
            {"indexed": False, "type": "uint256", "name": "loss"},
            {"indexed": False, "type": "uint256", "name": "totalGain"},
            {"indexed": False, "type": "uint256", "name": "totalLoss"},
            {"indexed": False, "type": "uint256", "name": "totalDebt"},
            {"indexed": False, "type": "uint256", "name": "debtAdded"},
            {"indexed": False, "type": "uint256", "name": "debtRatio"},
        ],
    },
]

STRATEGY_REPORTED_ABI = [
    V3_STRATEGY_REPORTED_EVENT,
    *V2_STRATEGY_REPORTED_EVENTS,
]

V2_DEPOSIT_EVENT = {
    "anonymous": False,
    "type": "event",
    "name": "Deposit",
    "inputs": [
        {"indexed": True, "type": "address", "name": "recipient"},
        {"indexed": False, "type": "uint256", "name": "shares"},
        {"indexed": False, "type": "uint256", "name": "amount"},
    ],
}

V2_WITHDRAW_EVENT = {
    "anonymous": False,
    "type": "event",
    "name": "Withdraw",
    "inputs": [
        {"indexed": True, "type": "address", "name": "recipient"},
        {"indexed": False, "type": "uint256", "name": "shares"},
        {"indexed": False, "type": "uint256", "name": "amount"},
    ],
}

V3_DEPOSIT_EVENT = {
    "anonymous": False,
    "type": "event",
    "name": "Deposit",
    "inputs": [
        {"indexed": True, "type": "address", "name": "sender"},
        {"indexed": True, "type": "address", "name": "owner"},
        {"indexed": False, "type": "uint256", "name": "assets"},
        {"indexed": False, "type": "uint256", "name": "shares"},
    ],
}

V3_WITHDRAW_EVENT = {
    "anonymous": False,
    "type": "event",
    "name": "Withdraw",
    "inputs": [
        {"indexed": True, "type": "address", "name": "sender"},
        {"indexed": True, "type": "address", "name": "receiver"},
        {"indexed": True, "type": "address", "name": "owner"},
        {"indexed": False, "type": "uint256", "name": "assets"},
        {"indexed": False, "type": "uint256", "name": "shares"},
    ],
}

ERC20_TRANSFER_EVENT = {
    "anonymous": False,
    "type": "event",
    "name": "Transfer",
    "inputs": [
        {"indexed": True, "type": "address", "name": "from"},
        {"indexed": True, "type": "address", "name": "to"},
        {"indexed": False, "type": "uint256", "name": "value"},
    ],
}

V3_DEBT_UPDATED_EVENT = {
    "anonymous": False,
    "type": "event",
    "name": "DebtUpdated",
    "inputs": [
        {"indexed": True, "type": "address", "name": "strategy"},
        {"indexed": False, "type": "uint256", "name": "current_debt"},
        {"indexed": False, "type": "uint256", "name": "new_debt"},
    ],
}

VAULT_FLOW_EVENTS = {
    "v2": [V2_DEPOSIT_EVENT, V2_WITHDRAW_EVENT],
    "v3": [V3_DEPOSIT_EVENT, V3_WITHDRAW_EVENT],
}

V3_DEBT_UPDATED_EVENTS = [V3_DEBT_UPDATED_EVENT]
