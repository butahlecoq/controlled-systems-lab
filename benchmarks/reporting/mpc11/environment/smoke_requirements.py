"""Exit status for the required optional-controller execution plugins."""


def qualification_exit_code(receipt: dict) -> int:
    return 0 if (receipt.get('ipopt_plugin_available') is True
                 and receipt.get('cvodes_plugin_available') is True) else 1
