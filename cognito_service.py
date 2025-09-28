"""
AWS Cognito integration service for user authentication and management.

This module provides functionality for:
- User registration with email verification
- User authentication with JWT tokens
- MFA (Multi-Factor Authentication) support
- Group-based permissions
- JWT token verification
"""

import boto3
import hmac
import hashlib
import base64
from typing import Optional, Dict, Any
from jose import jwt, JWTError
import requests
from botocore.exceptions import ClientError
from config import (
    COGNITO_USER_POOL_ID, 
    COGNITO_CLIENT_ID, 
    COGNITO_CLIENT_SECRET,
    COGNITO_REGION,
    AWS_REGION
)


class CognitoService:
    def __init__(self):
        self.client = boto3.client('cognito-idp', region_name=COGNITO_REGION)
        self.user_pool_id = COGNITO_USER_POOL_ID
        self.client_id = COGNITO_CLIENT_ID
        self.client_secret = COGNITO_CLIENT_SECRET
        self.region = COGNITO_REGION
        
        # Cache for JWT public keys
        self._jwt_keys = None
        
    def _get_secret_hash(self, username: str) -> str:
        """Generate secret hash for Cognito operations"""
        if not self.client_secret:
            return None
            
        message = username + self.client_id
        dig = hmac.new(
            str(self.client_secret).encode('utf-8'),
            msg=str(message).encode('utf-8'),
            digestmod=hashlib.sha256
        ).digest()
        return base64.b64encode(dig).decode()

    async def sign_up(self, username: str, password: str, email: str) -> Dict[str, Any]:
        """
        Register a new user with Cognito
        
        Args:
            username: Username for the new user
            password: Password for the new user
            email: Email address for the new user
            
        Returns:
            Dict containing user registration details
        """
        try:
            secret_hash = self._get_secret_hash(username)
            params = {
                'ClientId': self.client_id,
                'Username': username,
                'Password': password,
                'UserAttributes': [
                    {
                        'Name': 'email',
                        'Value': email
                    }
                ]
            }
            
            if secret_hash:
                params['SecretHash'] = secret_hash
                
            response = self.client.sign_up(**params)
            
            return {
                'success': True,
                'user_sub': response['UserSub'],
                'user_confirmed': response.get('UserConfirmed', False),
                'message': 'User registered successfully. Please check your email for verification code.'
            }
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            error_message = e.response['Error']['Message']
            
            return {
                'success': False,
                'error_code': error_code,
                'message': error_message
            }

    async def confirm_sign_up(self, username: str, confirmation_code: str) -> Dict[str, Any]:
        """
        Confirm user registration with verification code
        
        Args:
            username: Username to confirm
            confirmation_code: Verification code from email
            
        Returns:
            Dict containing confirmation result
        """
        try:
            secret_hash = self._get_secret_hash(username)
            params = {
                'ClientId': self.client_id,
                'Username': username,
                'ConfirmationCode': confirmation_code
            }
            
            if secret_hash:
                params['SecretHash'] = secret_hash
                
            self.client.confirm_sign_up(**params)
            
            # Add user to default User group
            await self.add_user_to_group(username, 'User')
            
            return {
                'success': True,
                'message': 'User confirmed successfully'
            }
            
        except ClientError as e:
            return {
                'success': False,
                'error_code': e.response['Error']['Code'],
                'message': e.response['Error']['Message']
            }

    async def authenticate(self, username: str, password: str) -> Dict[str, Any]:
        """
        Authenticate user and return JWT tokens
        
        Args:
            username: Username to authenticate
            password: User's password
            
        Returns:
            Dict containing authentication tokens and user info
        """
        try:
            secret_hash = self._get_secret_hash(username)
            params = {
                'ClientId': self.client_id,
                'AuthFlow': 'USER_PASSWORD_AUTH',
                'AuthParameters': {
                    'USERNAME': username,
                    'PASSWORD': password
                }
            }
            
            if secret_hash:
                params['AuthParameters']['SECRET_HASH'] = secret_hash
                
            response = self.client.initiate_auth(**params)
            
            # Handle MFA challenge if required
            if 'ChallengeName' in response:
                return {
                    'success': False,
                    'challenge': response['ChallengeName'],
                    'session': response['Session'],
                    'message': 'MFA challenge required'
                }
            
            # Get user groups
            user_groups = await self.get_user_groups(username)
            
            return {
                'success': True,
                'access_token': response['AuthenticationResult']['AccessToken'],
                'id_token': response['AuthenticationResult']['IdToken'],
                'refresh_token': response['AuthenticationResult']['RefreshToken'],
                'expires_in': response['AuthenticationResult']['ExpiresIn'],
                'groups': user_groups,
                'message': 'Authentication successful'
            }
            
        except ClientError as e:
            return {
                'success': False,
                'error_code': e.response['Error']['Code'],
                'message': e.response['Error']['Message']
            }

    async def respond_to_mfa_challenge(self, username: str, session: str, 
                                     challenge_name: str, mfa_code: str) -> Dict[str, Any]:
        """
        Respond to MFA challenge
        
        Args:
            username: Username
            session: Challenge session
            challenge_name: Type of MFA challenge
            mfa_code: MFA code from authenticator app
            
        Returns:
            Dict containing authentication result
        """
        try:
            secret_hash = self._get_secret_hash(username)
            params = {
                'ClientId': self.client_id,
                'ChallengeName': challenge_name,
                'Session': session,
                'ChallengeResponses': {
                    'USERNAME': username,
                    'SOFTWARE_TOKEN_MFA_CODE': mfa_code
                }
            }
            
            if secret_hash:
                params['ChallengeResponses']['SECRET_HASH'] = secret_hash
                
            response = self.client.respond_to_auth_challenge(**params)
            
            user_groups = await self.get_user_groups(username)
            
            return {
                'success': True,
                'access_token': response['AuthenticationResult']['AccessToken'],
                'id_token': response['AuthenticationResult']['IdToken'],
                'refresh_token': response['AuthenticationResult']['RefreshToken'],
                'expires_in': response['AuthenticationResult']['ExpiresIn'],
                'groups': user_groups,
                'message': 'MFA authentication successful'
            }
            
        except ClientError as e:
            return {
                'success': False,
                'error_code': e.response['Error']['Code'],
                'message': e.response['Error']['Message']
            }

    async def setup_mfa(self, access_token: str) -> Dict[str, Any]:
        """
        Set up MFA for a user
        
        Args:
            access_token: User's access token
            
        Returns:
            Dict containing MFA setup information
        """
        try:
            # Associate software token
            response = self.client.associate_software_token(
                AccessToken=access_token
            )
            
            return {
                'success': True,
                'secret_code': response['SecretCode'],
                'message': 'MFA setup initiated. Use the secret code to configure your authenticator app.'
            }
            
        except ClientError as e:
            return {
                'success': False,
                'error_code': e.response['Error']['Code'],
                'message': e.response['Error']['Message']
            }

    async def verify_mfa_setup(self, access_token: str, mfa_code: str) -> Dict[str, Any]:
        """
        Verify MFA setup with code from authenticator app
        
        Args:
            access_token: User's access token
            mfa_code: Code from authenticator app
            
        Returns:
            Dict containing verification result
        """
        try:
            self.client.verify_software_token(
                AccessToken=access_token,
                UserCode=mfa_code
            )
            
            # Enable MFA for the user
            self.client.set_user_mfa_preference(
                AccessToken=access_token,
                SoftwareTokenMfaSettings={
                    'Enabled': True,
                    'PreferredMfa': True
                }
            )
            
            return {
                'success': True,
                'message': 'MFA setup completed successfully'
            }
            
        except ClientError as e:
            return {
                'success': False,
                'error_code': e.response['Error']['Code'],
                'message': e.response['Error']['Message']
            }

    async def get_user_groups(self, username: str) -> list:
        """Get groups for a user"""
        try:
            response = self.client.admin_list_groups_for_user(
                UserPoolId=self.user_pool_id,
                Username=username
            )
            return [group['GroupName'] for group in response['Groups']]
        except ClientError:
            return []

    async def add_user_to_group(self, username: str, group_name: str) -> bool:
        """Add user to a group"""
        try:
            self.client.admin_add_user_to_group(
                UserPoolId=self.user_pool_id,
                Username=username,
                GroupName=group_name
            )
            return True
        except ClientError:
            return False

    async def remove_user_from_group(self, username: str, group_name: str) -> bool:
        """Remove user from a group"""
        try:
            self.client.admin_remove_user_from_group(
                UserPoolId=self.user_pool_id,
                Username=username,
                GroupName=group_name
            )
            return True
        except ClientError:
            return False

    async def get_jwt_keys(self) -> Dict[str, Any]:
        """Get JWT public keys for token verification"""
        if self._jwt_keys is None:
            url = f'https://cognito-idp.{self.region}.amazonaws.com/{self.user_pool_id}/.well-known/jwks.json'
            response = requests.get(url)
            self._jwt_keys = response.json()
        return self._jwt_keys

    async def verify_jwt_token(self, token: str) -> Optional[Dict[str, Any]]:
        """
        Verify JWT token and return payload
        
        Args:
            token: JWT token to verify
            
        Returns:
            Token payload if valid, None otherwise
        """
        try:
            # Get JWT keys
            keys = await self.get_jwt_keys()
            
            # Decode token header to get key ID
            unverified_header = jwt.get_unverified_header(token)
            key_id = unverified_header['kid']
            
            # Find the correct key
            key = None
            for k in keys['keys']:
                if k['kid'] == key_id:
                    key = k
                    break
                    
            if not key:
                return None
                
            # Verify token
            payload = jwt.decode(
                token,
                key,
                algorithms=['RS256'],
                audience=self.client_id,
                issuer=f'https://cognito-idp.{self.region}.amazonaws.com/{self.user_pool_id}'
            )
            
            return payload
            
        except JWTError:
            return None

    async def get_user_info(self, access_token: str) -> Optional[Dict[str, Any]]:
        """Get user information from access token"""
        try:
            response = self.client.get_user(AccessToken=access_token)
            
            # Extract user attributes
            user_info = {
                'username': response['Username'],
                'user_status': response.get('UserStatus'),
                'mfa_enabled': response.get('MFAOptions', []) != []
            }
            
            # Parse user attributes
            for attr in response['UserAttributes']:
                user_info[attr['Name']] = attr['Value']
                
            # Get user groups
            user_info['groups'] = await self.get_user_groups(response['Username'])
            
            return user_info
            
        except ClientError:
            return None

    async def exchange_code_for_tokens(self, code: str, redirect_uri: str) -> Optional[Dict[str, Any]]:
        """
        Exchange authorization code for tokens using Cognito OAuth endpoint
        
        Args:
            code: Authorization code from OAuth callback
            redirect_uri: The redirect URI used in the OAuth flow
            
        Returns:
            Dict containing access_token, id_token, refresh_token, and user info
        """
        try:
            from config import COGNITO_DOMAIN
            
            if not COGNITO_DOMAIN:
                return None
                
            # Prepare token exchange request
            token_url = f"https://{COGNITO_DOMAIN}.auth.{self.region}.amazoncognito.com/oauth2/token"
            
            # Prepare authentication header
            auth_string = f"{self.client_id}:{self.client_secret}"
            auth_bytes = auth_string.encode('utf-8')
            auth_header = base64.b64encode(auth_bytes).decode('utf-8')
            
            headers = {
                'Content-Type': 'application/x-www-form-urlencoded',
                'Authorization': f'Basic {auth_header}'
            }
            
            data = {
                'grant_type': 'authorization_code',
                'client_id': self.client_id,
                'code': code,
                'redirect_uri': redirect_uri
            }
            
            # Exchange code for tokens
            response = requests.post(token_url, headers=headers, data=data)
            
            if response.status_code != 200:
                print(f"Token exchange failed: {response.status_code} - {response.text}")
                return None
                
            token_data = response.json()
            
            # Get user information from the access token
            user_info = await self.get_user_info(token_data['access_token'])
            
            return {
                'success': True,
                'access_token': token_data['access_token'],
                'id_token': token_data.get('id_token'),
                'refresh_token': token_data.get('refresh_token'),
                'token_type': token_data.get('token_type', 'Bearer'),
                'expires_in': token_data.get('expires_in'),
                'user_info': user_info
            }
            
        except Exception as e:
            print(f"Error during token exchange: {str(e)}")
            return None


# Global instance
cognito_service = CognitoService()