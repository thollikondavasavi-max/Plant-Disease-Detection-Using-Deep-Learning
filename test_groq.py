#!/usr/bin/env python3
"""
Test script to verify Groq API connectivity and vision model functionality
"""

import os
from groq import Groq
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def test_groq_connection():
    """Test basic Groq API connection"""
    try:
        groq_client = Groq(api_key=os.getenv('GROQ_API_KEY'))
        
        # Test text completion
        response = groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": "Hello, can you respond with 'API working'?"}],
            max_tokens=10
        )
        
        print("✅ Groq API Connection: SUCCESS")
        print(f"Response: {response.choices[0].message.content}")
        return True
        
    except Exception as e:
        print("❌ Groq API Connection: FAILED")
        print(f"Error: {e}")
        return False

def test_current_models():
    """Test currently available models"""
    try:
        groq_client = Groq(api_key=os.getenv('GROQ_API_KEY'))
        
        # Test available text models
        current_models = [
            "llama-3.1-8b-instant",
            "llama-3.3-70b-versatile"
        ]
        
        for model in current_models:
            try:
                response = groq_client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": "Hello, respond with 'Working'"}],
                    max_tokens=10
                )
                print(f"✅ Model {model}: {response.choices[0].message.content}")
            except Exception as e:
                print(f"❌ Model {model}: {e}")
                
    except Exception as e:
        print(f"❌ Model test failed: {e}")

def test_plant_chat():
    """Test plant care chat functionality"""
    try:
        groq_client = Groq(api_key=os.getenv('GROQ_API_KEY'))
        
        response = groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": "You are a plant care expert."},
                {"role": "user", "content": "My plant has yellow leaves, what could be wrong?"}
            ],
            max_tokens=100
        )
        
        print("✅ Plant Chat Test:")
        print(f"Response: {response.choices[0].message.content}")
        return True
        
    except Exception as e:
        print(f"❌ Plant chat test failed: {e}")
        return False

if __name__ == "__main__":
    print("Testing Groq API Integration...")
    print("=" * 50)
    
    # Check API key
    api_key = os.getenv('GROQ_API_KEY')
    if not api_key:
        print("❌ GROQ_API_KEY not found in environment variables")
        exit(1)
    else:
        print(f"✅ API Key found: {api_key[:10]}...")
    
    print()
    
    # Test connection
    if test_groq_connection():
        print()
        test_current_models()
        print()
        test_plant_chat()
    
    print("\nTest complete!")