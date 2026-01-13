import google.generativeai as genai
import os
import io
from PIL import Image
import base64
from typing import Optional, Union
import logging

class GeminiClient:
    def __init__(self):
        self.api_key = os.getenv('GEMINI_API_KEY')
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY not found in environment variables")
        
        genai.configure(api_key=self.api_key)
        self.model = genai.GenerativeModel('gemini-2.0-flash-exp')
        
        # Aspect ratio dimensions
        self.dimensions = {
            'banner_3_1': (1200, 400),  # 3:1 ratio
            'pfp_1_1': (1000, 1000)     # 1:1 ratio
        }
    
    def generate_ascii_art(self, text: str, aspect_ratio: str) -> Optional[bytes]:
        """Generate ASCII art from text"""
        try:
            prompt = f"""
Create ASCII art of the text "{text}" using monospace characters. Requirements:
- Aspect ratio: {aspect_ratio} exactly
- High contrast, clean edges
- No borders, watermarks, or labels
- Professional appearance suitable for Dexscreener
- Centered composition with proper padding
- Output as image file
"""
            
            response = self.model.generate_content(prompt)
            
            if response.parts and len(response.parts) > 0:
                # Try to get image from response
                for part in response.parts:
                    if hasattr(part, 'inline_data') and part.inline_data:
                        image_data = part.inline_data.data
                        return self._ensure_aspect_ratio(image_data, aspect_ratio)
            
            # If no image in response, try to generate image from text
            image_prompt = f"""
Create a professional ASCII art style image of "{text}" in {aspect_ratio} format.
Use monospace font characters, high contrast, clean appearance.
No text labels or watermarks.
"""
            return self._generate_image_from_prompt(image_prompt, aspect_ratio)
            
        except Exception as e:
            logging.error(f"Error generating ASCII art: {e}")
            return None
    
    def enhance_image(self, image_data: bytes, aspect_ratio: str, custom_prompt: str = None) -> Optional[bytes]:
        """Enhance or extend existing image"""
        try:
            # Convert bytes to PIL Image
            image = Image.open(io.BytesIO(image_data))
            
            if custom_prompt:
                prompt = f"""
Analyze the provided image and transform it to {aspect_ratio} format based on this instruction: {custom_prompt}

Requirements:
- Maintain high quality and professional appearance
- Ensure seamless blending
- No text, lettering, watermarks, or labels unless specifically requested
- Output: High quality {aspect_ratio} image
"""
            else:
                prompt = f"""
Analyze the provided image and transform it to {aspect_ratio} format:

IF the image contains a logo, icon, or graphic element:
- Extend using a plain colored background
- Match the EXACT background color from the original image
- Maintain identical background color throughout entire output
- Keep the main element centered and properly scaled
- Create photorealistic quality
- NO text, lettering, watermarks, or labels

IF the image is a photograph or scene:
- Extend naturally maintaining the same artistic style
- Keep original composition and subject matter
- Match lighting, color grading, and atmosphere
- Ensure seamless blending with no visible seams
- Maintain photorealistic quality
- NO text, lettering, watermarks, or labels

Output: High quality {aspect_ratio} image
"""
            
            # Prepare input
            inputs = [prompt, image]
            
            response = self.model.generate_content(inputs)
            
            if response.parts and len(response.parts) > 0:
                for part in response.parts:
                    if hasattr(part, 'inline_data') and part.inline_data:
                        enhanced_data = part.inline_data.data
                        return self._ensure_aspect_ratio(enhanced_data, aspect_ratio)
            
            return None
            
        except Exception as e:
            logging.error(f"Error enhancing image: {e}")
            return None
    
    def generate_from_text(self, prompt: str, aspect_ratio: str) -> Optional[bytes]:
        """Generate image from text description"""
        try:
            full_prompt = f"""
Create a professional image based on this description: "{prompt}"

Technical Requirements:
- Aspect ratio: {aspect_ratio} EXACTLY - non-negotiable
- High quality, professional appearance
- Suitable for cryptocurrency/Dexscreener platform
- NO text, lettering, or watermarks unless explicitly requested in prompt
- Clean composition with proper visual balance
- Output as high-resolution image file
"""
            
            return self._generate_image_from_prompt(full_prompt, aspect_ratio)
            
        except Exception as e:
            logging.error(f"Error generating image from text: {e}")
            return None
    
    def _generate_image_from_prompt(self, prompt: str, aspect_ratio: str) -> Optional[bytes]:
        """Helper method to generate image from prompt"""
        try:
            response = self.model.generate_content(prompt)
            
            if response.parts and len(response.parts) > 0:
                for part in response.parts:
                    if hasattr(part, 'inline_data') and part.inline_data:
                        image_data = part.inline_data.data
                        return self._ensure_aspect_ratio(image_data, aspect_ratio)
            
            return None
            
        except Exception as e:
            logging.error(f"Error in _generate_image_from_prompt: {e}")
            return None
    
    def _ensure_aspect_ratio(self, image_data: bytes, aspect_ratio: str) -> bytes:
        """Ensure image has correct aspect ratio"""
        try:
            image = Image.open(io.BytesIO(image_data))
            
            target_width, target_height = self.dimensions[aspect_ratio]
            
            # Resize to exact dimensions
            resized_image = image.resize((target_width, target_height), Image.Resampling.LANCZOS)
            
            # Convert back to bytes
            output = io.BytesIO()
            resized_image.save(output, format='PNG', quality=95)
            output.seek(0)
            
            return output.getvalue()
            
        except Exception as e:
            logging.error(f"Error ensuring aspect ratio: {e}")
            return image_data  # Return original if processing fails
    
    def get_quota_status(self) -> dict:
        """Check API quota status (basic implementation)"""
        # This is a simplified version - in production you'd use actual quota APIs
        return {
            'available': True,
            'remaining': 'unknown',
            'resets_in': 'unknown'
        }
