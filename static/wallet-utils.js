/**
 * Wallet Utilities for TEE Agent
 * Handles MetaMask/Web3 wallet connections and interactions
 */

class WalletManager {
    constructor(chainConfig = null) {
        this.provider = null;
        this.signer = null;
        this.address = null;
        this.chainConfig = chainConfig; // Will be set dynamically from API
        this.chainId = chainConfig ? chainConfig.chain_id : null;
        this.connected = false;
    }

    /**
     * Check if MetaMask is installed
     */
    isMetaMaskInstalled() {
        return typeof window.ethereum !== 'undefined';
    }

    /**
     * Connect to MetaMask wallet
     */
    async connect() {
        if (!this.isMetaMaskInstalled()) {
            throw new Error('MetaMask is not installed. Please install MetaMask to continue.');
        }

        try {
            // Request account access
            const accounts = await window.ethereum.request({
                method: 'eth_requestAccounts'
            });

            this.address = accounts[0];
            this.provider = window.ethereum;
            this.connected = true;

            // Get current chain ID
            const chainId = await window.ethereum.request({
                method: 'eth_chainId'
            });

            // Check if on correct network
            if (parseInt(chainId, 16) !== this.chainId) {
                await this.switchNetwork();
            }

            // Listen for account changes
            window.ethereum.on('accountsChanged', (accounts) => {
                this.address = accounts[0];
                window.location.reload();
            });

            // Listen for chain changes
            window.ethereum.on('chainChanged', () => {
                window.location.reload();
            });

            return this.address;
        } catch (error) {
            console.error('Failed to connect wallet:', error);
            throw new Error('Failed to connect wallet: ' + error.message);
        }
    }

    /**
     * Switch to configured network
     */
    async switchNetwork() {
        if (!this.chainConfig) {
            throw new Error('Chain configuration not loaded');
        }

        try {
            await window.ethereum.request({
                method: 'wallet_switchEthereumChain',
                params: [{ chainId: this.chainConfig.chain_id_hex }],
            });
        } catch (switchError) {
            // This error code indicates that the chain has not been added to MetaMask
            if (switchError.code === 4902) {
                try {
                    await window.ethereum.request({
                        method: 'wallet_addEthereumChain',
                        params: [{
                            chainId: this.chainConfig.chain_id_hex,
                            chainName: this.chainConfig.chain_name,
                            nativeCurrency: this.chainConfig.native_currency,
                            rpcUrls: this.chainConfig.rpc_urls,
                            blockExplorerUrls: this.chainConfig.block_explorer_urls
                        }]
                    });
                } catch (addError) {
                    throw new Error(`Failed to add ${this.chainConfig.chain_name} network: ` + addError.message);
                }
            } else {
                throw new Error('Failed to switch network: ' + switchError.message);
            }
        }
    }

    /**
     * Send ETH to an address
     */
    async sendTransaction(toAddress, amountInEth) {
        if (!this.connected) {
            throw new Error('Wallet not connected');
        }

        try {
            const amountInWei = '0x' + (BigInt(Math.floor(amountInEth * 1e18))).toString(16);

            const transactionParameters = {
                from: this.address,
                to: toAddress,
                value: amountInWei,
            };

            const txHash = await window.ethereum.request({
                method: 'eth_sendTransaction',
                params: [transactionParameters],
            });

            return txHash;
        } catch (error) {
            console.error('Transaction failed:', error);
            throw new Error('Transaction failed: ' + error.message);
        }
    }

    /**
     * Get balance of an address
     */
    async getBalance(address) {
        if (!this.provider) {
            throw new Error('Provider not initialized');
        }

        try {
            const balance = await window.ethereum.request({
                method: 'eth_getBalance',
                params: [address, 'latest'],
            });

            // Convert from wei to ETH
            const balanceInEth = parseInt(balance, 16) / 1e18;
            return balanceInEth;
        } catch (error) {
            console.error('Failed to get balance:', error);
            throw new Error('Failed to get balance: ' + error.message);
        }
    }

    /**
     * Disconnect wallet
     */
    disconnect() {
        this.provider = null;
        this.signer = null;
        this.address = null;
        this.connected = false;
    }
}

/**
 * API Utilities for TEE Agent
 * Handles API calls with better error handling
 */
class APIClient {
    constructor(baseURL = '') {
        this.baseURL = baseURL;
    }

    /**
     * Make API request with error handling
     */
    async request(endpoint, options = {}) {
        const url = this.baseURL + endpoint;

        try {
            const response = await fetch(url, {
                ...options,
                headers: {
                    'Content-Type': 'application/json',
                    ...options.headers,
                },
            });

            const data = await response.json();

            if (!response.ok) {
                const errorMessage = data.detail || data.error || `HTTP ${response.status}: ${response.statusText}`;
                throw new Error(errorMessage);
            }

            return { success: true, data };
        } catch (error) {
            console.error(`API Error [${endpoint}]:`, error);
            return {
                success: false,
                error: error.message || 'Unknown error occurred',
            };
        }
    }

    /**
     * GET request
     */
    async get(endpoint) {
        return this.request(endpoint, { method: 'GET' });
    }

    /**
     * POST request
     */
    async post(endpoint, body = {}) {
        return this.request(endpoint, {
            method: 'POST',
            body: JSON.stringify(body),
        });
    }

    /**
     * Get chain configuration
     */
    async getChainConfig() {
        return this.get('/api/chain-config');
    }

    /**
     * Get wallet info
     */
    async getWallet() {
        return this.get('/api/wallet');
    }

    /**
     * Get agent status
     */
    async getStatus() {
        return this.get('/api/status');
    }

    /**
     * Register agent
     */
    async registerAgent() {
        return this.post('/api/register');
    }

    /**
     * Register TEE
     */
    async registerTEE() {
        return this.post('/api/tee/register');
    }

    /**
     * Sign a message
     */
    async signMessage(message) {
        return this.post('/api/sign', { message });
    }

    /**
     * Process a task
     */
    async processTask(taskId, query, data = {}, parameters = {}) {
        return this.post('/api/process', {
            task_id: taskId,
            query,
            data,
            parameters,
        });
    }

    /**
     * Get agent card
     */
    async getAgentCard() {
        return this.get('/api/card');
    }

    /**
     * Get attestation
     */
    async getAttestation() {
        return this.get('/api/attestation');
    }
}

/**
 * UI Utilities
 */
class UIUtils {
    /**
     * Show loading state
     */
    static showLoading(elementId, message = 'Loading...') {
        const element = document.getElementById(elementId);
        if (element) {
            element.innerHTML = `
                <div class="flex items-center gap-2">
                    <div class="animate-spin rounded-full h-4 w-4 border-t-2 border-b-2 border-blue-500"></div>
                    <span class="text-gray-400">${message}</span>
                </div>
            `;
        }
    }

    /**
     * Show error message
     */
    static showError(elementId, message, retryFunction = null) {
        const element = document.getElementById(elementId);
        if (element) {
            const retryButton = retryFunction
                ? `<button onclick="${retryFunction.name}()" class="bg-blue-600 hover:bg-blue-700 px-4 py-2 rounded text-sm mt-2">Retry</button>`
                : '';

            element.innerHTML = `
                <p class="text-red-400 mb-2">❌ Error</p>
                <p class="text-sm text-gray-300 mb-2">${message}</p>
                ${retryButton}
            `;
        }
    }

    /**
     * Show success message
     */
    static showSuccess(elementId, message) {
        const element = document.getElementById(elementId);
        if (element) {
            element.innerHTML = `
                <p class="text-green-400 mb-2">✓ ${message}</p>
            `;
        }
    }

    /**
     * Format address for display
     */
    static formatAddress(address) {
        if (!address) return '';
        return `${address.substring(0, 6)}...${address.substring(address.length - 4)}`;
    }

    /**
     * Format ETH amount
     */
    static formatEth(amount) {
        return parseFloat(amount).toFixed(4);
    }

    /**
     * Copy to clipboard
     */
    static async copyToClipboard(text) {
        try {
            await navigator.clipboard.writeText(text);
            return true;
        } catch (error) {
            console.error('Failed to copy:', error);
            return false;
        }
    }

    /**
     * Show toast notification
     */
    static showToast(message, type = 'info') {
        const colors = {
            info: 'bg-blue-600',
            success: 'bg-green-600',
            error: 'bg-red-600',
            warning: 'bg-yellow-600'
        };

        const toast = document.createElement('div');
        toast.className = `fixed bottom-4 right-4 ${colors[type]} text-white px-6 py-3 rounded-lg shadow-lg z-50 transition-opacity duration-300`;
        toast.textContent = message;
        document.body.appendChild(toast);

        setTimeout(() => {
            toast.style.opacity = '0';
            setTimeout(() => toast.remove(), 300);
        }, 3000);
    }
}

// Export for use in other files
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { WalletManager, APIClient, UIUtils };
}
