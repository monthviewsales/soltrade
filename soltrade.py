from soltrade.wallet import find_balance
from soltrade.config import config
from soltrade.trading import start_trading
from soltrade.log import log_general

# Initialize configuration
config()

def check_json_state() -> bool:
    if config().keypair and config().secondary_mint:
        return True
    return False

# Prints "Soltrade" and information about the connected wallet
print(r"""                    $$\   $$\                              $$\           
                    $$ |  $$ |                             $$ |          
 $$$$$$$\  $$$$$$\  $$ |$$$$$$\    $$$$$$\  $$$$$$\   $$$$$$$ | $$$$$$\  
$$  _____|$$  __$$\ $$ |\_$$  _|  $$  __$$\ \____$$\ $$  __$$ |$$  __$$\ 
\$$$$$$\  $$ /  $$ |$$ |  $$ |    $$ |  \__|$$$$$$$ |$$ /  $$ |$$$$$$$$ |
 \____$$\ $$ |  $$ |$$ |  $$ |$$\ $$ |     $$  __$$ |$$ |  $$ |$$   ____|
$$$$$$$  |\$$$$$$  |$$ |  \$$$$  |$$ |     \$$$$$$$ |\$$$$$$$ |\$$$$$$$\ 
\_______/  \______/ \__|   \____/ \__|      \_______| \_______| \_______|
""")
can_run = check_json_state()

# Error catching in case the program is unable to find the properties of the wallet
try:
    log_general.info(f"Soltrade has detected {find_balance(config().primary_mint)} {config().primary_mint_symbol} tokens available for trading.")
except Exception as e:
    log_general.error(f"Error finding {config().primary_mint_symbol} balance: {e}")
    exit()

# Checks if the run prompt should be displayed
if can_run:
    log_general.debug("Soltrade has successfully imported the API requirements.")
    start_trading()
else:
    exit()