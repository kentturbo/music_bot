import sys
from vkpymusic import TokenReceiver

def main():
    print("=== VKontakte Music Token Receiver ===")
    print("This script will help you get the VK_TOKEN and VK_USER_AGENT for your .env file.")
    print("Your credentials are only sent directly to VKontakte API endpoints.\n")
    
    login = input("Enter VK Login (phone number or email): ").strip()
    password = input("Enter VK Password: ").strip()
    
    receiver = TokenReceiver(login, password)
    
    print("\nAuthenticating with VKontakte...")
    if not receiver.auth():
        print("\nAuthentication failed. Please check your credentials.")
        sys.exit(1)
        
    token = receiver.get_token()
    user_agent = receiver.get_user_agent()
    
    print("\n=== SUCCESS ===")
    print("Copy and paste these values into your .env file:\n")
    print(f"VK_TOKEN={token}")
    print(f"VK_USER_AGENT={user_agent}")
    print("\nAfter updating .env, rebuild and restart the bot.")

if __name__ == "__main__":
    main()
