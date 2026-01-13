import requests
import os
import base64
import requests
import logging
import io
import json
from PIL import Image, ImageDraw, ImageFont
from typing import Optional

class OpenRouterClient:
    def __init__(self):
        self.api_key = os.getenv('OPENROUTER_API_KEY')
        if not self.api_key:
            raise ValueError("OPENROUTER_API_KEY not found in environment variables")
        
        self.api_url = "https://openrouter.ai/api/v1/chat/completions"
        self.model = "google/gemini-2.5-flash-image-preview"
        
        # Aspect ratio dimensions
        self.dimensions = {
            'banner_3_1': (1500, 500),  # 3:1 ratio
            'pfp_1_1': (1000, 1000),    # 1:1 ratio
            '3:1': (1500, 500),        # Alternative format
            '1:1': (1000, 1000)        # Alternative format
        }
    
    def _image_to_base64(self, image_path: str) -> str:
        """Convert image file to base64 string"""
        with open(image_path, 'rb') as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')
    
    def generate_ascii_art(self, text: str, aspect_ratio: str) -> Optional[bytes]:
        """Generate ASCII art using pyfiglet (no AI needed)"""
        try:
            from pyfiglet import Figlet
            from datetime import datetime
            
            logging.info(f"Generating ASCII art for: {text}")
            
            # Generate ASCII art using 'standard' font (uses letters)
            f = Figlet(font='standard')
            ascii_text = f.renderText(text)
            
            logging.info(f"ASCII text generated: {len(ascii_text)} characters")
            
            # Create image canvas
            if aspect_ratio in ['3:1', 'banner_3_1']:
                width, height = 1500, 500
            else:  # 1:1
                width, height = 1000, 1000
            
            # Create black canvas
            img = Image.new('RGB', (width, height), color='black')
            draw = ImageDraw.Draw(img)
            
            # Try to load a monospace font with larger size
            font = None
            font_paths = [
                "cour.ttf",  # Windows Courier
                "courier.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",  # Linux
                "/System/Library/Fonts/Courier.dfont"  # Mac
            ]
            
            for font_path in font_paths:
                try:
                    font = ImageFont.truetype(font_path, 36)  # Even larger font
                    break
                except:
                    continue
            
            if font is None:
                font = ImageFont.load_default()
            
            # Calculate text size for centering
            bbox = draw.textbbox((0, 0), ascii_text, font=font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
            
            # Center the text
            x = (width - text_width) // 2
            y = (height - text_height) // 2
            
            # Draw centered white text
            draw.text((x, y), ascii_text, fill='white', font=font)
            
            # Convert to bytes
            img_byte_arr = io.BytesIO()
            img.save(img_byte_arr, format='PNG', quality=95)
            return img_byte_arr.getvalue()
            
        except Exception as e:
            logging.error(f"Error generating ASCII art: {e}")
            return None
    
    def enhance_image(self, image_path: str, aspect_ratio: str, custom_prompt: str = None) -> Optional[bytes]:
        """Enhance or extend existing image using OpenRouter"""
        try:
            width, height = self.dimensions.get(aspect_ratio, (1000, 1000))
            
            # Convert image to base64
            base64_image = self._image_to_base64(image_path)
            image_data_url = f"data:image/jpeg;base64,{base64_image}"
            
            # Build the prompt
            if custom_prompt:
                prompt = f"""
                Analyze the provided image and transform it to {aspect_ratio} format based on this instruction: {custom_prompt}
                
                Requirements:
                - Maintain high quality and professional appearance
                - Ensure seamless blending
                - No text, lettering, watermarks, or labels unless specifically requested
                - Output: High quality {width}x{height} image
                """
            else:
                prompt = """I need you to EDIT and EXTEND this uploaded image to create a 3:1 aspect ratio banner (approximately 1536x672 pixels).

CRITICAL EDITING INSTRUCTIONS:
- PRESERVE the uploaded image content exactly as it appears
- DO NOT redraw, regenerate, or reinterpret the main subject
- EXTEND the canvas in ALL DIRECTIONS (top, bottom, left, AND right) until it fills the entire 3:1 banner format
- Fill ALL extended areas by naturally continuing the background, sky, ground, and environment
- Match the background color, lighting, and texture perfectly in all extended areas
- Keep the main subject in the center, unchanged
- Create seamless transitions between original and extended areas on all sides
- Maintain photorealistic quality throughout
- The ENTIRE 3:1 canvas must be filled with actual image content - no bars, no padding, no empty space

This is an IMAGE EDITING task, not image generation. The original uploaded content must remain intact and recognizable while the canvas expands around it."""
            
            # Prepare API request
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://t.me/karwa_banner_bot"
            }
            
            request_body = {
                "model": self.model,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": image_data_url
                                }
                            },
                            {
                                "type": "text",
                                "text": prompt
                            }
                        ]
                    }
                ],
                "modalities": ["image", "text"],
                "image_config": {
                    "aspect_ratio": "21:9" if aspect_ratio in ['3:1', 'banner_3_1'] else "1:1"
                },
                "max_tokens": 8192,
                "temperature": 0.7
            }
            
            logging.info(f"Calling OpenRouter API for image enhancement")
            
            # Make API call
            response = requests.post(
                self.api_url,
                headers=headers,
                json=request_body,
                timeout=60
            )
            
            if response.status_code == 402:
                raise Exception("Insufficient credits")
            elif response.status_code == 429:
                raise Exception("Rate limit exceeded")
            elif response.status_code != 200:
                raise Exception(f"API error: {response.status_code} - {response.text}")
            
            # Parse response
            response_data = response.json()
            
            # DEBUG: Log response structure for enhance_image
            logging.info(f"Response status: {response.status_code}")
            logging.info(f"Response keys: {response_data.keys()}")
            logging.info(f"Full response structure: {json.dumps(response_data, indent=2)[:1000]}")
            
            # Extract image from response
            if 'choices' in response_data and len(response_data['choices']) > 0:
                message = response_data['choices'][0]['message']
                
                # Images are in the 'images' array
                if 'images' in message and len(message['images']) > 0:
                    # Get first image
                    first_image = message['images'][0]
                    
                    # Extract base64 data URL
                    image_data_url = first_image['image_url']['url']
                    # Format: "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAA..."
                    
                    # Split to get just the base64 part
                    if ',' in image_data_url:
                        base64_data = image_data_url.split(',', 1)[1]
                    else:
                        base64_data = image_data_url
                    
                    # Decode base64 to bytes
                    image_bytes = base64.b64decode(base64_data)
                    
                    logging.info(f"Successfully extracted and decoded image ({len(image_bytes)} bytes)")
                    return image_bytes
                else:
                    raise Exception("No images in API response")
            else:
                raise Exception("No choices in API response")
            
        except Exception as e:
            logging.error(f"Error enhancing image: {e}")
            raise
    
    def generate_from_text(self, prompt: str, aspect_ratio: str) -> Optional[bytes]:
        """Generate image from text description using OpenRouter"""
        try:
            width, height = self.dimensions.get(aspect_ratio, (1000, 1000))
            
            full_prompt = f"""
Create a professional image based on this description: "{prompt}"

Technical Requirements:
- Aspect ratio: {aspect_ratio} EXACTLY - non-negotiable
- High quality, professional appearance
- Suitable for cryptocurrency/Dexscreener platform
- NO text, lettering, or watermarks unless explicitly requested in prompt
- Clean composition with proper visual balance
- Output as high-resolution image file
- Maintain photorealistic quality if applicable
"""
            
            return self._generate_image_from_prompt(full_prompt, width, height)
            
        except Exception as e:
            logging.error(f"Error generating image from text: {e}")
            return None
    
    def _generate_image_from_prompt(self, prompt: str, width: int, height: int) -> Optional[bytes]:
        """Helper method to generate image from prompt using OpenRouter"""
        try:
            logging.info(f"Calling OpenRouter API for text-to-image generation")
            
            # Prepare API request
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://t.me/karwa_banner_bot"
            }
            
            request_body = {
                "model": self.model,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": prompt
                            }
                        ]
                    }
                ],
                "modalities": ["image", "text"],
                "image_config": {
                    "aspect_ratio": "21:9" if width > height else "1:1"
                },
                "max_tokens": 8192,
                "temperature": 0.7
            }
            
            # Make API call
            response = requests.post(
                self.api_url,
                headers=headers,
                json=request_body,
                timeout=60
            )
            
            if response.status_code == 402:
                raise Exception("Insufficient credits")
            elif response.status_code == 429:
                raise Exception("Rate limit exceeded")
            elif response.status_code != 200:
                raise Exception(f"API error: {response.status_code} - {response.text}")
            
            # Parse response
            response_data = response.json()
            
            # DEBUG: Log response structure for text-to-image
            logging.info(f"Response status: {response.status_code}")
            logging.info(f"Response keys: {response_data.keys()}")
            logging.info(f"Full response structure: {json.dumps(response_data, indent=2)[:1000]}")
            
            # Extract image from response
            if 'choices' in response_data and len(response_data['choices']) > 0:
                message = response_data['choices'][0]['message']
                
                # Images are in the 'images' array
                if 'images' in message and len(message['images']) > 0:
                    # Get first image
                    first_image = message['images'][0]
                    
                    # Extract base64 data URL
                    image_data_url = first_image['image_url']['url']
                    # Format: "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAA..."
                    
                    # Split to get just the base64 part
                    if ',' in image_data_url:
                        base64_data = image_data_url.split(',', 1)[1]
                    else:
                        base64_data = image_data_url
                    
                    # Decode base64 to bytes
                    image_bytes = base64.b64decode(base64_data)
                    
                    logging.info(f"Successfully extracted and decoded image ({len(image_bytes)} bytes)")
                    return image_bytes
                else:
                    raise Exception("No images in API response")
            else:
                raise Exception("No choices in API response")
            
        except Exception as e:
            logging.error(f"Error in _generate_image_from_prompt: {e}")
            raise
    
    def get_quota_status(self) -> dict:
        """Check API quota status"""
        # This is a simplified version - in production you'd use actual quota APIs
        return {
            'available': True,
            'remaining': 'unknown',
            'resets_in': 'unknown'
        }
