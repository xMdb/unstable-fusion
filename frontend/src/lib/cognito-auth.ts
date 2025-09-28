/**
 * AWS Cognito Authentication Service
 * Handles user authentication, registration, MFA, and token management
 */

export interface CognitoUser {
  username: string;
  email: string;
  email_verified: boolean;
  groups: string[];
  mfa_enabled: boolean;
  user_status: string;
}

export interface AuthTokens {
  access_token: string;
  id_token: string;
  refresh_token: string;
  expires_in: number;
  token_type: string;
  groups: string[];
}

export interface MFAChallenge {
  challenge: string;
  session: string;
  message: string;
}

export interface SignUpResponse {
  message: string;
  user_confirmed: boolean;
}

export interface AuthResponse {
  success: boolean;
  message?: string;
  data?: AuthTokens;
  challenge?: MFAChallenge;
}

class CognitoAuthService {
  private baseUrl: string;
  private tokens: AuthTokens | null = null;
  private user: CognitoUser | null = null;

  constructor(baseUrl = '/') {
    this.baseUrl = baseUrl;
    this.loadFromStorage();
  }

  // Token storage management
  private saveToStorage(tokens: AuthTokens): void {
    localStorage.setItem('cognito_tokens', JSON.stringify(tokens));
    localStorage.setItem('cognito_expires_at', (Date.now() + tokens.expires_in * 1000).toString());
  }

  private loadFromStorage(): void {
    try {
      const stored = localStorage.getItem('cognito_tokens');
      const expiresAt = localStorage.getItem('cognito_expires_at');
      
      if (stored && expiresAt) {
        const tokens = JSON.parse(stored);
        const expires = parseInt(expiresAt);
        
        if (Date.now() < expires) {
          this.tokens = tokens;
        } else {
          this.clearStorage();
        }
      }
    } catch (error) {
      console.error('Error loading tokens from storage:', error);
      this.clearStorage();
    }
  }

  private clearStorage(): void {
    localStorage.removeItem('cognito_tokens');
    localStorage.removeItem('cognito_expires_at');
    localStorage.removeItem('cognito_user');
    this.tokens = null;
    this.user = null;
  }

  // Authentication methods
  async signUp(username: string, password: string, email: string): Promise<SignUpResponse> {
    const response = await fetch(`${this.baseUrl}auth/signup`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password, email })
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Registration failed');
    }

    return await response.json();
  }

  async confirmSignUp(username: string, confirmationCode: string): Promise<void> {
    const response = await fetch(`${this.baseUrl}auth/confirm`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ 
        username, 
        confirmation_code: confirmationCode 
      })
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Confirmation failed');
    }
  }

  async signIn(username: string, password: string): Promise<AuthResponse> {
    try {
      const response = await fetch(`${this.baseUrl}auth/login`, {
        method: 'POST',
        credentials: 'include', // Include cookies
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password })
      });

      if (response.status === 202) {
        // MFA challenge required
        const challengeData = await response.json();
        return {
          success: false,
          challenge: challengeData
        };
      }

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Login failed');
      }

      const tokens: AuthTokens = await response.json();
      this.tokens = tokens;
      this.saveToStorage(tokens);
      
      // Get user info
      await this.getCurrentUser();

      return {
        success: true,
        data: tokens
      };
    } catch (error) {
      return {
        success: false,
        message: error instanceof Error ? error.message : 'Login failed'
      };
    }
  }

  async respondToMFAChallenge(
    username: string, 
    session: string, 
    challengeName: string, 
    mfaCode: string
  ): Promise<AuthResponse> {
    try {
      const response = await fetch(`${this.baseUrl}auth/mfa/challenge`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          username,
          session,
          challenge_name: challengeName,
          mfa_code: mfaCode
        })
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'MFA verification failed');
      }

      const tokens: AuthTokens = await response.json();
      this.tokens = tokens;
      this.saveToStorage(tokens);
      
      // Get user info
      await this.getCurrentUser();

      return {
        success: true,
        data: tokens
      };
    } catch (error) {
      return {
        success: false,
        message: error instanceof Error ? error.message : 'MFA verification failed'
      };
    }
  }

  async getCurrentUser(): Promise<CognitoUser | null> {
    try {
      // First try with cookies (for Cognito OAuth flow)
      const response = await fetch(`${this.baseUrl}auth/me`, {
        credentials: 'include' // Include cookies
      });

      if (response.ok) {
        this.user = await response.json();
        localStorage.setItem('cognito_user', JSON.stringify(this.user));
        return this.user;
      }

      // If cookie auth failed and we have tokens, try with token
      if (this.tokens) {
        const tokenResponse = await fetch(`${this.baseUrl}auth/me`, {
          headers: { 'Authorization': `Bearer ${this.tokens.id_token}` }
        });

        if (tokenResponse.ok) {
          this.user = await tokenResponse.json();
          localStorage.setItem('cognito_user', JSON.stringify(this.user));
          return this.user;
        }
      }

      // If both methods failed with 401, clear auth state
      if (response.status === 401) {
        this.signOut();
      }
      
      return null;
    } catch (error) {
      console.error('Error getting current user:', error);
      return null;
    }
  }

  // Check if user is authenticated via server (using cookies)
  async checkServerAuthentication(): Promise<boolean> {
    try {
      const response = await fetch(`${this.baseUrl}auth/me`, {
        credentials: 'include' // Include cookies
      });
      
      if (response.ok) {
        const user = await response.json();
        this.user = user;
        localStorage.setItem('cognito_user', JSON.stringify(user));
        return true;
      }
      
      return false;
    } catch (error) {
      console.error('Error checking server authentication:', error);
      return false;
    }
  }

  async signOut(): Promise<void> {
    try {
      // Call the server logout endpoint to clear HTTP-only cookies
      await fetch(`${this.baseUrl}auth/logout`, {
        method: 'POST',
        credentials: 'include', // Include cookies to clear them
        headers: {
          'Content-Type': 'application/json',
        },
      });
    } catch (error) {
      console.error('Error calling logout endpoint:', error);
    }
    
    // Clear client-side storage
    this.clearStorage();
  }

  // Google OAuth
  async getGoogleOAuthUrl(): Promise<string> {
    const response = await fetch(`${this.baseUrl}auth/federated/google`);
    const data = await response.json();
    return data.oauth_url;
  }

  // Check authentication with server (for cookie-based auth)
  async checkServerAuth(): Promise<boolean> {
    try {
      // Add cache-busting parameter to avoid browser caching issues
      const cacheBust = Date.now();
      const response = await fetch(`${this.baseUrl}auth/me?_=${cacheBust}`, {
        method: 'GET',
        credentials: 'include', // Include cookies
        headers: {
          'Content-Type': 'application/json',
          'Cache-Control': 'no-cache',
          'Pragma': 'no-cache'
        }
      });
      
      if (response.ok) {
        const userData = await response.json();
        // Store user data so UserProfile component can access it
        this.user = {
          username: userData.username,
          email: userData.email,
          email_verified: userData.email_verified || false,
          groups: userData.groups || [],
          mfa_enabled: userData.mfa_enabled || false,
          user_status: userData.user_status || 'CONFIRMED'
        };
        return true;
      }
      return false;
    } catch (error) {
      console.error('Server auth check failed:', error);
      return false;
    }
  }

  // Utility methods
  isAuthenticated(): boolean {
    // Check localStorage tokens first
    return this.tokens !== null && Date.now() < this.getTokenExpiration();
  }

  getTokenExpiration(): number {
    const stored = localStorage.getItem('cognito_expires_at');
    return stored ? parseInt(stored) : 0;
  }

  getIdToken(): string | null {
    return this.tokens?.id_token || null;
  }

  getAccessToken(): string | null {
    return this.tokens?.access_token || null;
  }

  getUserGroups(): string[] {
    return this.user?.groups || this.tokens?.groups || [];
  }

  isAdmin(): boolean {
    return this.getUserGroups().includes('Admin');
  }

  getUser(): CognitoUser | null {
    return this.user;
  }

  // API call helper with authentication
  async authenticatedFetch(url: string, options: RequestInit = {}): Promise<Response> {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      ...(options.headers as Record<string, string>)
    };

    // If we have a token, include it in the Authorization header
    const token = this.getIdToken();
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }

    const response = await fetch(url, {
      ...options,
      headers,
      credentials: 'include' // Include cookies for Cognito auth
    });

    if (response.status === 401) {
      this.signOut();
      throw new Error('Authentication expired');
    }

    return response;
  }
}

// Export singleton instance
export const cognitoAuth = new CognitoAuthService();
export default cognitoAuth;