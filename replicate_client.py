import replicate
import os
import requests
import tempfile
import logging
from typing import Optional
from PIL import Image
import io

class ReplicateClient:
    def __init__(self):
        self.api_token = os.getenv('REPLICATE_API_TOKEN')
        if not self.api_token:
            raise ValueError("REPLICATE_API_TOKEN not found in environment variables")
        
        # Set the API token for Replicate
        os.environ['REPLICATE_API_TOKEN'] = self.api_token
        
        # Model to use for image generation
        self.model = "stability-ai/sdxl:39ed52f2a78e934b3ba6e2a89f5b1c712de7dfea535525255b1aa35c5565e08b"
        
        # Aspect ratio dimensions
        self.dimensions = {
            'banner_3_1': (1500, 500),  # 3:1 ratio
            'pfp_1_1': (1000, 1000),    # 1:1 ratio
            '3:1': (1500, 500),        # Alternative format
            '1:1': (1000, 1000)        # Alternative format
        }
    
    def generate_ascii_art(self, text: str, aspect_ratio: str) -> Optional[bytes]:
        """Generate ASCII art from text using Replicate"""
        try:
            width, height = self.dimensions.get(aspect_ratio, (1000, 1000))
            
            prompt = f"""
            Create a professional ASCII art style image of "{text}" in {aspect_ratio} format.
            Use monospace font characters, high contrast, clean appearance.
            No text labels or watermarks.
            Professional appearance suitable for Dexscreener.
            """
            
            return self._generate_image_from_prompt(prompt, width, height)
            
        except Exception as e:
            logging.error(f"Error generating ASCII art: {e}")
            return None
    
    def enhance_image(self, image_path: str, aspect_ratio: str, custom_prompt: str = None) -> Optional[bytes]:
        """Enhance or extend existing image using Replicate"""
        try:
            width, height = self.dimensions.get(aspect_ratio, (1000, 1000))
            
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
                prompt = f"""
                Extend this image to {width}x{height} pixels maintaining the original content.
                
                If this is a logo or icon with solid background: extend the background color naturally, keep the main element centered.
                
                If this is a photograph: extend the scene naturally maintaining composition, lighting, and style.
                
                Important: No text, no watermarks, no labels. Professional quality. Seamless extension.
                """
            
            # Call Replicate API
            logging.info(f"Calling Replicate API for image enhancement")
            
            output = replicate.run(
                self.model,
                input={
                    "image": open(image_path, "rb"),
                    "prompt": prompt,
                    "negative_prompt": "text, watermark, signature, label, writing, letters",
                    "width": width,
                    "height": height,
                    "num_inference_steps": 40,
                    "guidance_scale": 7.5,
                    "prompt_strength": 0.45,
                    "scheduler": "DDIM"
                }
            )
            
            # Replicate returns a URL to the generated image
            if isinstance(output, list) and len(output) > 0:
                image_url = output[0]
            elif isinstance(output, str):
                image_url = output
            else:
                raise Exception(f"Unexpected output format from Replicate: {type(output)}")
            
            # Download the generated image
            response = requests.get(image_url)
            response.raise_for_status()
            
            return response.content
            
        except Exception as e:
            logging.error(f"Error enhancing image: {e}")
            return None
    
    def generate_from_text(self, prompt: str, aspect_ratio: str) -> Optional[bytes]:
        """Generate image from text description using Replicate"""
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
            - Output as high-resolution {width}x{height} image file
            """
            
            return self._generate_image_from_prompt(full_prompt, width, height)
            
        except Exception as e:
            logging.error(f"Error generating image from text: {e}")
            return None
    
    def _generate_image_from_prompt(self, prompt: str, width: int, height: int) -> Optional[bytes]:
        """Helper method to generate image from prompt using Replicate"""
        try:
            logging.info(f"Calling Replicate API for text-to-image generation")
            
            output = replicate.run(
                self.model,
                input={
                    "prompt": prompt,
                    "negative_prompt": "text, watermark, signature, label, writing, letters",
                    "width": width,
                    "height": height,
                    "num_inference_steps": 40,
                    "guidance_scale": 7.5,
                    "scheduler": "DDIM"
                }
            )
            
            # Replicate returns a URL to the generated image
            if isinstance(output, list) and len(output) > 0:
                image_url = output[0]
            elif isinstance(output, str):
                image_url = output
            else:
                raise Exception(f"Unexpected output format from Replicate: {type(output)}")
            
            # Download the generated image
            response = requests.get(image_url)
            response.raise_for_status()
            
            return response.content
            
        except Exception as e:
            logging.error(f"Error in _generate_image_from_prompt: {e}")
            return None
    
    def get_quota_status(self) -> dict:
        """Check API quota status"""
        # This is a simplified version - in production you'd use actual quota APIs
        return {
            'available': True,
            'remaining': 'unknown',
            'resets_in': 'unknown'
        }
