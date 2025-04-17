#!/usr/bin/env python3
"""
Benchmark script to compare audio generation time between:
1. ElevenLabs
2. AWS Polly with standard voices
3. AWS Polly with generative voices

This script measures the time it takes to generate audio for the same text using different TTS services.
"""

import os
import time
import json
import boto3
import logging
import requests
from typing import Dict, List, Tuple, Any
import tempfile
import statistics
import pathlib

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Sample texts for testing
SAMPLE_TEXTS = {
    "short": "Welcome to TensorTours! This is a short sample for testing text-to-speech services.",
    "medium": """
    Welcome to San Francisco's iconic Golden Gate Bridge! This engineering marvel, completed in 1937, 
    spans almost 1.7 miles across the Golden Gate Strait. Its distinctive International Orange color was 
    originally meant to be a primer, but the consulting architect was so impressed with the vibrant hue against 
    the backdrop of the bay that it became permanent. The bridge took four years to build and was the longest 
    suspension bridge in the world at the time of its completion.
    """,
    "long": """
    Welcome to San Francisco's iconic Golden Gate Bridge! This engineering marvel, completed in 1937, 
    spans almost 1.7 miles across the Golden Gate Strait. Its distinctive International Orange color was 
    originally meant to be a primer, but the consulting architect was so impressed with the vibrant hue against 
    the backdrop of the bay that it became permanent. The bridge took four years to build and was the longest 
    suspension bridge in the world at the time of its completion.
    
    The Golden Gate Bridge is not only a vital transportation link but also one of the most photographed structures 
    in the world. It connects San Francisco to Marin County and carries both vehicles and pedestrians. The bridge's 
    design had to account for strong ocean currents, frequent fog, and the possibility of earthquakes. Its two main 
    cables, each more than 36 inches in diameter, contain 27,572 strands of wire, enough to circle the earth three times!
    
    Walking across the bridge offers spectacular panoramic views of the city, Alcatraz Island, and the Pacific Ocean. 
    On clear days, you can see as far as the Farallon Islands, 30 miles offshore. The bridge's 746-foot tall towers were 
    the tallest structures in San Francisco until 1972. The Golden Gate Bridge is an enduring symbol of American innovation 
    and the pioneering spirit of the West Coast, attracting over 10 million visitors annually.
    
    Interestingly, the Golden Gate Bridge is constantly being painted to protect it from the corrosive effects of salt air. 
    A team of painters works year-round, starting at one end and working their way to the other, only to begin again in a 
    continuous cycle. This maintenance is crucial for preserving the structural integrity of this beloved landmark that has 
    become synonymous with San Francisco itself.
    """
}

# AWS Polly configuration
class PollyService:
    def __init__(self, output_dir=None):
        self.polly_client = boto3.client('polly')
        self.s3_client = boto3.client('s3')
        self.output_dir = output_dir
        
    def generate_audio_standard(self, text: str, voice_id: str = "Amy") -> Tuple[float, int, bytes]:
        """Generate audio using AWS Polly standard voice"""
        start_time = time.time()
        
        response = self.polly_client.synthesize_speech(
            Engine="standard",
            LanguageCode='en-GB',
            OutputFormat='mp3',
            Text=text,
            TextType='text',
            VoiceId=voice_id
        )
        
        # Get audio stream
        audio_stream = response['AudioStream'].read()
        
        # Calculate time and size
        elapsed_time = time.time() - start_time
        audio_size = len(audio_stream)
        
        return elapsed_time, audio_size, audio_stream
    
    def generate_audio_neural(self, text: str, voice_id: str = "Amy") -> Tuple[float, int, bytes]:
        """Generate audio using AWS Polly neural voice"""
        start_time = time.time()
        
        response = self.polly_client.synthesize_speech(
            Engine="neural",
            LanguageCode='en-GB',
            OutputFormat='mp3',
            Text=text,
            TextType='text',
            VoiceId=voice_id
        )
        
        # Get audio stream
        audio_stream = response['AudioStream'].read()
        
        # Calculate time and size
        elapsed_time = time.time() - start_time
        audio_size = len(audio_stream)
        
        return elapsed_time, audio_size, audio_stream
        
    def generate_audio_generative(self, text: str, voice_id: str = "Amy") -> Tuple[float, int, bytes]:
        """Generate audio using AWS Polly generative voice"""
        start_time = time.time()
        
        # Generative AI voices need to be used with long-form or neural-tts-conversational
        response = self.polly_client.synthesize_speech(
            Engine="generative",
            LanguageCode='en-GB',
            OutputFormat='mp3',
            Text=text,
            TextType='text',
            VoiceId=voice_id
        )
        
        # Get audio stream
        audio_stream = response['AudioStream'].read()
        
        # Calculate time and size
        elapsed_time = time.time() - start_time
        audio_size = len(audio_stream)
        
        return elapsed_time, audio_size, audio_stream

# ElevenLabs configuration
class ElevenLabsService:
    def __init__(self, api_key: str = None, output_dir=None):
        self.api_key = api_key or os.environ.get("ELEVENLABS_API_KEY")
        if not self.api_key:
            logger.warning("No ElevenLabs API key provided. ElevenLabs tests will be skipped.")
        self.base_url = "https://api.elevenlabs.io/v1"
        self.output_dir = output_dir
        
    def generate_audio(self, text: str, voice_id: str = "21m00Tcm4TlvDq8ikWAM") -> Tuple[float, int, bytes]:
        """Generate audio using ElevenLabs API"""
        if not self.api_key:
            return None, 0, None
            
        start_time = time.time()
        
        url = f"{self.base_url}/text-to-speech/{voice_id}"
        
        headers = {
            "Accept": "audio/mpeg",
            "Content-Type": "application/json",
            "xi-api-key": self.api_key
        }
        
        data = {
            "text": text,
            "model_id": "eleven_monolingual_v1",
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.75
            }
        }
        
        try:
            response = requests.post(url, json=data, headers=headers)
            response.raise_for_status()
            
            audio_content = response.content
            
            # Calculate time and size
            elapsed_time = time.time() - start_time
            audio_size = len(audio_content)
            
            return elapsed_time, audio_size, audio_content
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error with ElevenLabs API: {str(e)}")
            return None, 0, None

def save_audio_file(audio_data, filename, directory="audio_samples"):
    """Save audio data to a file with verification"""
    if audio_data is None:
        logger.warning(f"No audio data to save for {filename}")
        return None
        
    # Create absolute directory path
    abs_dir = os.path.abspath(directory)
    logger.info(f"Saving to directory: {abs_dir}")
    
    # Create directory if it doesn't exist
    os.makedirs(abs_dir, exist_ok=True)
    
    # Create absolute file path
    file_path = os.path.join(abs_dir, filename)
    
    try:
        # Write the file
        with open(file_path, "wb") as f:
            f.write(audio_data)
        
        # Verify file was created
        if os.path.exists(file_path):
            file_size = os.path.getsize(file_path)
            logger.info(f"Successfully saved audio file: {file_path} ({file_size} bytes)")
            return file_path
        else:
            logger.error(f"Failed to verify file creation: {file_path}")
            return None
    except Exception as e:
        logger.exception(f"Error saving audio file {filename}: {str(e)}")
        return None

def run_benchmark(num_runs: int = 3):
    """Run benchmark tests for all services and text lengths"""
    
    # Create output directory (absolute path)
    output_dir = os.path.abspath("audio_samples")
    logger.info(f"Output directory for audio samples: {output_dir}")
    os.makedirs(output_dir, exist_ok=True)
    
    # Check if directory was created successfully
    if not os.path.exists(output_dir):
        logger.error(f"Failed to create output directory {output_dir}")
        return {}
    
    # Initialize services
    polly_service = PollyService(output_dir=output_dir)
    elevenlabs_service = ElevenLabsService(output_dir=output_dir)
    
    results = {
        "aws_polly_standard": {},
        "aws_polly_neural": {},
        "aws_polly_generative": {},
        "elevenlabs": {}
    }
    
    # Run tests for each text length
    for text_type, text in SAMPLE_TEXTS.items():
        logger.info(f"Testing with {text_type} text ({len(text)} characters)")
        
        # AWS Polly standard
        standard_times = []
        standard_sizes = []
        for i in range(num_runs):
            logger.info(f"  AWS Polly Standard - Run {i+1}/{num_runs}")
            elapsed_time, audio_size, audio_data = polly_service.generate_audio_standard(text)
            standard_times.append(elapsed_time)
            standard_sizes.append(audio_size)
            
            # Save the last run's audio file
            if i == num_runs - 1:
                save_audio_file(audio_data, f"polly_standard_{text_type}.mp3")
            
        # AWS Polly neural
        neural_times = []
        neural_sizes = []
        for i in range(num_runs):
            logger.info(f"  AWS Polly Neural - Run {i+1}/{num_runs}")
            elapsed_time, audio_size, audio_data = polly_service.generate_audio_neural(text)
            neural_times.append(elapsed_time)
            neural_sizes.append(audio_size)
            
            # Save the last run's audio file
            if i == num_runs - 1:
                save_audio_file(audio_data, f"polly_neural_{text_type}.mp3")
        # AWS Polly generative
        generative_times = []
        generative_sizes = []
        try:
            for i in range(num_runs):
                logger.info(f"  AWS Polly Generative - Run {i+1}/{num_runs}")
                elapsed_time, audio_size, audio_data = polly_service.generate_audio_generative(text)
                generative_times.append(elapsed_time)
                generative_sizes.append(audio_size)
                
                # Save the last run's audio file
                if i == num_runs - 1:
                    save_audio_file(audio_data, f"polly_generative_{text_type}.mp3")
        except Exception as e:
            logger.error(f"Error with AWS Polly Generative: {str(e)}")
            
        # ElevenLabs
        '''
        elevenlabs_times = []
        elevenlabs_sizes = []
        if elevenlabs_service.api_key:
            for i in range(num_runs):
                logger.info(f"  ElevenLabs - Run {i+1}/{num_runs}")
                elapsed_time, audio_size, audio_data = elevenlabs_service.generate_audio(text)
                if elapsed_time is not None:
                    elevenlabs_times.append(elapsed_time)
                    elevenlabs_sizes.append(audio_size)
                    
                    # Save the last run's audio file
                    if i == num_runs - 1:
                        save_audio_file(audio_data, f"elevenlabs_{text_type}.mp3")
        '''
        
        # Store results
        results["aws_polly_standard"][text_type] = {
            "avg_time": statistics.mean(standard_times) if standard_times else None,
            "min_time": min(standard_times) if standard_times else None,
            "max_time": max(standard_times) if standard_times else None,
            "avg_size": statistics.mean(standard_sizes) if standard_sizes else None
        }
        
        results["aws_polly_neural"][text_type] = {
            "avg_time": statistics.mean(neural_times) if neural_times else None,
            "min_time": min(neural_times) if neural_times else None,
            "max_time": max(neural_times) if neural_times else None,
            "avg_size": statistics.mean(neural_sizes) if neural_sizes else None
        }
        results["aws_polly_generative"][text_type] = {
            "avg_time": statistics.mean(generative_times) if generative_times else None,
            "min_time": min(generative_times) if generative_times else None,
            "max_time": max(generative_times) if generative_times else None,
            "avg_size": statistics.mean(generative_sizes) if generative_sizes else None
        }
        
        '''
        results["elevenlabs"][text_type] = {
            "avg_time": statistics.mean(elevenlabs_times) if elevenlabs_times else None,
            "min_time": min(elevenlabs_times) if elevenlabs_times else None,
            "max_time": max(elevenlabs_times) if elevenlabs_times else None,
            "avg_size": statistics.mean(elevenlabs_sizes) if elevenlabs_sizes else None
        }
        '''
    
    return results

def display_results(results):
    """Display benchmark results in a readable format"""
    print("\n" + "="*80)
    print("TTS SERVICE BENCHMARK RESULTS".center(80))
    print("="*80)
    
    for text_type in SAMPLE_TEXTS.keys():
        print(f"\n{text_type.upper()} TEXT ({len(SAMPLE_TEXTS[text_type])} characters):")
        print("-"*80)
        print(f"{'Service':<25} {'Avg Time (s)':<15} {'Min Time (s)':<15} {'Max Time (s)':<15} {'Avg Size (KB)':<15}")
        print("-"*80)
        
        for service_name, service_results in results.items():
            if text_type in service_results:
                result = service_results[text_type]
                avg_time = f"{result['avg_time']:.2f}" if result['avg_time'] is not None else "N/A"
                min_time = f"{result['min_time']:.2f}" if result['min_time'] is not None else "N/A"
                max_time = f"{result['max_time']:.2f}" if result['max_time'] is not None else "N/A"
                avg_size = f"{result['avg_size']/1024:.2f}" if result['avg_size'] is not None else "N/A"
                
                print(f"{service_name.replace('_', ' ').title():<25} {avg_time:<15} {min_time:<15} {max_time:<15} {avg_size:<15}")
        
        print("-"*80)
    
    print("\nNOTES:")
    print("* Times are in seconds, sizes are in kilobytes")
    print("* Lower times are better")
    print("* ElevenLabs results may be missing if no API key was provided")
    print("* AWS Polly Generative results may be missing if the service is not available in your region")

if __name__ == "__main__":
    print("\nStarting TTS service benchmark...")
    print("This will test ElevenLabs and AWS Polly (standard, neural, and generative) voices.")
    print("For ElevenLabs tests to work, set the ELEVENLABS_API_KEY environment variable.")
    print("Testing with short, medium, and long text samples.")
    print("\nRunning benchmark (this may take a few minutes)...")
    
    # Run the benchmark with 3 runs for each configuration
    results = run_benchmark(num_runs=3)
    
    # Display results
    display_results(results)
    
    # Save results to file
    with open("tts_benchmark_results.json", "w") as f:
        json.dump(results, f, indent=2)
    
    print(f"\nResults saved to tts_benchmark_results.json")
    print(f"Audio samples saved to the 'audio_samples' directory")
