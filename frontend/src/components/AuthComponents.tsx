import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';
import { Eye, EyeOff, Chrome, Shield, Users } from 'lucide-react';
import { cognitoAuth, type AuthResponse, type MFAChallenge } from '@/lib/cognito-auth';

interface LoginFormProps {
  onLoginSuccess: () => void;
}

export function LoginForm({ onLoginSuccess }: LoginFormProps) {
  const [isLogin, setIsLogin] = useState(true);
  const [formData, setFormData] = useState({
    username: '',
    password: '',
    email: '',
    confirmationCode: ''
  });
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [mfaChallenge, setMfaChallenge] = useState<MFAChallenge | null>(null);
  const [mfaCode, setMfaCode] = useState('');
  const [needsConfirmation, setNeedsConfirmation] = useState(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  const handleInputChange = (field: string, value: string) => {
    setFormData(prev => ({ ...prev, [field]: value }));
    setMessage(null);
  };

  const handleSignUp = async () => {
    if (!formData.username || !formData.password || !formData.email) {
      setMessage({ type: 'error', text: 'Please fill in all fields' });
      return;
    }

    setLoading(true);
    try {
      const response = await cognitoAuth.signUp(
        formData.username,
        formData.password,
        formData.email
      );
      
      if (response.user_confirmed) {
        setMessage({ type: 'success', text: 'Registration successful! You can now log in.' });
        setIsLogin(true);
      } else {
        setNeedsConfirmation(true);
        setMessage({ type: 'success', text: response.message });
      }
    } catch (error) {
      setMessage({ type: 'error', text: error instanceof Error ? error.message : 'Registration failed' });
    } finally {
      setLoading(false);
    }
  };

  const handleConfirmSignUp = async () => {
    if (!formData.username || !formData.confirmationCode) {
      setMessage({ type: 'error', text: 'Please enter username and confirmation code' });
      return;
    }

    setLoading(true);
    try {
      await cognitoAuth.confirmSignUp(formData.username, formData.confirmationCode);
      setMessage({ type: 'success', text: 'Email confirmed successfully! You can now log in.' });
      setNeedsConfirmation(false);
      setIsLogin(true);
    } catch (error) {
      setMessage({ type: 'error', text: error instanceof Error ? error.message : 'Confirmation failed' });
    } finally {
      setLoading(false);
    }
  };

  const handleSignIn = async () => {
    if (!formData.username || !formData.password) {
      setMessage({ type: 'error', text: 'Please enter username and password' });
      return;
    }

    setLoading(true);
    try {
      const response: AuthResponse = await cognitoAuth.signIn(formData.username, formData.password);
      
      if (response.success) {
        setMessage({ type: 'success', text: 'Login successful!' });
        onLoginSuccess();
      } else if (response.challenge) {
        setMfaChallenge(response.challenge);
        setMessage({ type: 'success', text: 'Please enter your MFA code' });
      } else {
        setMessage({ type: 'error', text: response.message || 'Login failed' });
      }
    } catch (error) {
      setMessage({ type: 'error', text: error instanceof Error ? error.message : 'Login failed' });
    } finally {
      setLoading(false);
    }
  };

  const handleMFAResponse = async () => {
    if (!mfaChallenge || !mfaCode) {
      setMessage({ type: 'error', text: 'Please enter MFA code' });
      return;
    }

    setLoading(true);
    try {
      const response = await cognitoAuth.respondToMFAChallenge(
        formData.username,
        mfaChallenge.session,
        mfaChallenge.challenge,
        mfaCode
      );

      if (response.success) {
        setMessage({ type: 'success', text: 'MFA verification successful!' });
        onLoginSuccess();
      } else {
        setMessage({ type: 'error', text: response.message || 'MFA verification failed' });
      }
    } catch (error) {
      setMessage({ type: 'error', text: error instanceof Error ? error.message : 'MFA verification failed' });
    } finally {
      setLoading(false);
    }
  };

  const handleGoogleSignIn = async () => {
    try {
      const oauthUrl = await cognitoAuth.getGoogleOAuthUrl();
      window.location.href = oauthUrl;
    } catch (error) {
      setMessage({ type: 'error', text: 'Google sign-in not available' });
    }
  };

  // MFA Challenge Form
  if (mfaChallenge) {
    return (
      <Card className="w-full max-w-md mx-auto">
        <CardHeader className="text-center">
          <CardTitle className="flex items-center justify-center gap-2">
            <Shield className="h-5 w-5" />
            Multi-Factor Authentication
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {message && (
            <Alert className={message.type === 'error' ? 'border-red-500' : 'border-green-500'}>
              <AlertDescription className={message.type === 'error' ? 'text-red-700' : 'text-green-700'}>
                {message.text}
              </AlertDescription>
            </Alert>
          )}
          
          <div className="space-y-2">
            <label className="text-sm font-medium">Enter code from your authenticator app:</label>
            <Input
              type="text"
              placeholder="123456"
              value={mfaCode}
              onChange={(e) => setMfaCode(e.target.value)}
              maxLength={6}
              className="text-center text-lg tracking-widest"
            />
          </div>

          <div className="flex gap-2">
            <Button
              variant="outline"
              onClick={() => {
                setMfaChallenge(null);
                setMfaCode('');
                setMessage(null);
              }}
              className="flex-1"
            >
              Back
            </Button>
            <Button
              onClick={handleMFAResponse}
              disabled={loading || mfaCode.length !== 6}
              className="flex-1"
            >
              {loading ? 'Verifying...' : 'Verify'}
            </Button>
          </div>
        </CardContent>
      </Card>
    );
  }

  // Email Confirmation Form
  if (needsConfirmation) {
    return (
      <Card className="w-full max-w-md mx-auto">
        <CardHeader className="text-center">
          <CardTitle>Confirm Your Email</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {message && (
            <Alert className={message.type === 'error' ? 'border-red-500' : 'border-green-500'}>
              <AlertDescription className={message.type === 'error' ? 'text-red-700' : 'text-green-700'}>
                {message.text}
              </AlertDescription>
            </Alert>
          )}
          
          <div className="space-y-2">
            <label className="text-sm font-medium">Username:</label>
            <Input
              type="text"
              value={formData.username}
              onChange={(e) => handleInputChange('username', e.target.value)}
              placeholder="Enter your username"
            />
          </div>

          <div className="space-y-2">
            <label className="text-sm font-medium">Confirmation Code:</label>
            <Input
              type="text"
              value={formData.confirmationCode}
              onChange={(e) => handleInputChange('confirmationCode', e.target.value)}
              placeholder="Enter code from email"
            />
          </div>

          <div className="flex gap-2">
            <Button
              variant="outline"
              onClick={() => {
                setNeedsConfirmation(false);
                setIsLogin(false);
              }}
              className="flex-1"
            >
              Back
            </Button>
            <Button
              onClick={handleConfirmSignUp}
              disabled={loading}
              className="flex-1"
            >
              {loading ? 'Confirming...' : 'Confirm'}
            </Button>
          </div>
        </CardContent>
      </Card>
    );
  }

  // Main Login/Registration Form
  return (
    <Card className="w-full max-w-md mx-auto">
      <CardHeader className="text-center">
        <CardTitle>Unstable Fusion</CardTitle>
        <p className="text-sm text-muted-foreground">
          AI-powered image generation service with Stable Diffusion models
        </p>
      </CardHeader>
      <CardContent>
        <Tabs value={isLogin ? 'login' : 'register'} className="w-full">
          <TabsList className="grid w-full grid-cols-2">
            <TabsTrigger value="login" onClick={() => setIsLogin(true)}>
              Login
            </TabsTrigger>
            <TabsTrigger value="register" onClick={() => setIsLogin(false)}>
              Register
            </TabsTrigger>
          </TabsList>

          <div className="mt-4 space-y-4">
            {message && (
              <Alert className={message.type === 'error' ? 'border-red-500' : 'border-green-500'}>
                <AlertDescription className={message.type === 'error' ? 'text-red-700' : 'text-green-700'}>
                  {message.text}
                </AlertDescription>
              </Alert>
            )}

            <TabsContent value="login" className="space-y-4 mt-4">
              <div className="space-y-2">
                <label className="text-sm font-medium">Username:</label>
                <Input
                  type="text"
                  value={formData.username}
                  onChange={(e) => handleInputChange('username', e.target.value)}
                  placeholder="Enter your username"
                />
              </div>

              <div className="space-y-2">
                <label className="text-sm font-medium">Password:</label>
                <div className="relative">
                  <Input
                    type={showPassword ? 'text' : 'password'}
                    value={formData.password}
                    onChange={(e) => handleInputChange('password', e.target.value)}
                    placeholder="Enter your password"
                  />
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    className="absolute right-0 top-0 h-full px-3 py-2 hover:bg-transparent"
                    onClick={() => setShowPassword(!showPassword)}
                  >
                    {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </Button>
                </div>
              </div>

              <Button
                onClick={handleSignIn}
                disabled={loading}
                className="w-full"
              >
                {loading ? 'Signing In...' : 'Sign In'}
              </Button>

              <div className="relative">
                <div className="absolute inset-0 flex items-center">
                  <Separator className="w-full" />
                </div>
                <div className="relative flex justify-center text-xs uppercase">
                  <span className="bg-background px-2 text-muted-foreground">
                    Or continue with
                  </span>
                </div>
              </div>

              <Button
                variant="outline"
                onClick={handleGoogleSignIn}
                className="w-full"
              >
                <Chrome className="mr-2 h-4 w-4" />
                Sign in with Google
              </Button>
            </TabsContent>

            <TabsContent value="register" className="space-y-4 mt-4">
              <div className="space-y-2">
                <label className="text-sm font-medium">Username:</label>
                <Input
                  type="text"
                  value={formData.username}
                  onChange={(e) => handleInputChange('username', e.target.value)}
                  placeholder="Choose a username"
                />
              </div>

              <div className="space-y-2">
                <label className="text-sm font-medium">Email:</label>
                <Input
                  type="email"
                  value={formData.email}
                  onChange={(e) => handleInputChange('email', e.target.value)}
                  placeholder="Enter your email"
                />
              </div>

              <div className="space-y-2">
                <label className="text-sm font-medium">Password:</label>
                <div className="relative">
                  <Input
                    type={showPassword ? 'text' : 'password'}
                    value={formData.password}
                    onChange={(e) => handleInputChange('password', e.target.value)}
                    placeholder="Create a password"
                  />
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    className="absolute right-0 top-0 h-full px-3 py-2 hover:bg-transparent"
                    onClick={() => setShowPassword(!showPassword)}
                  >
                    {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </Button>
                </div>
                <p className="text-xs text-muted-foreground">
                  Password must contain at least 8 characters with uppercase, lowercase, number, and symbol
                </p>
              </div>

              <Button
                onClick={handleSignUp}
                disabled={loading}
                className="w-full"
              >
                {loading ? 'Creating Account...' : 'Create Account'}
              </Button>
            </TabsContent>
          </div>
        </Tabs>
      </CardContent>
    </Card>
  );
}

interface UserProfileProps {
  onSignOut: () => void;
}

export function UserProfile({ onSignOut }: UserProfileProps) {
  const user = cognitoAuth.getUser();
  const isAdmin = cognitoAuth.isAdmin();

  if (!user) return null;

  return (
    <div className="flex items-center justify-between p-4 bg-muted/50 rounded-lg">
      <div className="flex items-center gap-3">
        <div className="w-8 h-8 bg-primary rounded-full flex items-center justify-center text-primary-foreground text-sm font-medium">
          {user.username.charAt(0).toUpperCase()}
        </div>
        <div>
          <div className="flex items-center gap-2">
            <span className="font-medium">{user.username}</span>
            {isAdmin && (
              <Badge variant="destructive" className="text-xs">
                <Users className="w-3 h-3 mr-1" />
                Admin
              </Badge>
            )}
          </div>
          <div className="text-sm text-muted-foreground">{user.email}</div>
        </div>
      </div>
      <Button variant="outline" size="sm" onClick={onSignOut}>
        Sign Out
      </Button>
    </div>
  );
}