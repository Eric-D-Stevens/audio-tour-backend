# TensorTours Backend

## What is TensorTours?

TensorTours is an AI-powered audio tour application that provides personalized, location-based audio guides for travelers and tourists. The app allows users to discover points of interest near their location, learn about historical and cultural sites, and experience cities in a new way through AI-generated audio content.

With TensorTours, users can:
- Select tour durations (30-180 minutes)
- Choose from various categories (History, Art, Culture, Food & Drink, Architecture, Nature)
- Get real-time, location-aware audio content about nearby attractions
- View high-quality photos of places with proper attribution via Google Places API
- Create customized tours based on their interests and available time

## Backend Repository Role

This repository contains the server-side infrastructure and API implementation for TensorTours. The backend is responsible for:

1. **Audio Content Generation**: AI-powered services that generate tour narration and descriptions
2. **Tour Creation Logic**: Algorithms for creating personalized tours based on user preferences and location
3. **API Endpoints**: RESTful services that the mobile app consumes
4. **Data Processing**: Processing location data and points of interest
5. **Authentication Services**: Integration with Amazon Cognito for user authentication

### Key Components

- Python-based serverless architecture
- AWS Lambda functions for various microservices
- Integration with external APIs (Google Places, etc.)
- Testing infrastructure for both unit and integration tests
- Deployment scripts and configuration

### Getting Started

1. Set up a Python virtual environment:
   ```
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

2. Install dependencies:
   ```
   pip install -e .
   ```

3. Configure environment variables (copy .env.example to .env and fill in values)

4. Run tests:
   ```
   pytest
   ```

### Development Workflow

- Use `format.sh` for code formatting
- Run `check.sh` to execute quality checks before committing
- Follow test-driven development practices using the tests directory

## Architecture

The backend follows a microservices architecture with Lambda functions handling specific aspects of the application logic. The tour generation system uses AI models to create compelling and accurate audio content about locations around the world.
