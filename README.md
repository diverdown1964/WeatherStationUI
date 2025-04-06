# Weather Station Configuration UI

A simple Azure Functions application that will serve as the backend for the Weather Station Configuration UI.

## Prerequisites

- Python 3.9 or higher
- Azure Functions Core Tools version 4.x
- Azure CLI (for deployment)
- Visual Studio Code with Azure Functions extension (recommended)

## Local Development

1. Create a virtual environment:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows use: .venv\Scripts\activate
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Run the function locally:
   ```bash
   func start
   ```

4. Test the endpoint:
   ```bash
   curl http://localhost:7071/api/hello
   ```

## Deployment

1. Sign in to Azure:
   ```bash
   az login
   ```

2. Create a Function App in Azure Portal or using Azure CLI

3. Deploy using Azure Functions Core Tools:
   ```bash
   func azure functionapp publish <your-function-app-name>
   ```

## Endpoints

- `GET /api/hello`: Returns a welcome message
  - Response: "Hello, World! Welcome to the Weather Station Configuration UI."
  - Status: 200 OK

## Project Structure

- `function_app.py`: Main application file containing the function endpoints
- `requirements.txt`: Python dependencies
- `host.json`: Host configuration
- `local.settings.json`: Local settings (not committed to source control)

## Authentication

The application requires authentication when running in Azure, while local development remains unauthenticated. Access is restricted to users from the same Azure AD tenant as the application.

### Azure Authentication Setup

1. Enable Authentication in Azure Portal:
   - Go to your Function App in the Azure Portal
   - Navigate to "Authentication" under Settings
   - Click "Add identity provider"
   - Select "Microsoft" as the identity provider
   - Configure the following settings:
     - App registration type: "Create new app registration"
     - Name: "weather-config-ui-auth"
     - Supported account types: "Accounts in this organizational directory only"
     - App ID: (will be auto-generated)
     - Client secret: (will be auto-generated)
     - Allow unauthenticated access: Yes (for local development)
     - Token store: Yes
     - Click "Add"

2. Required Environment Variables:
   - `AZURE_CLIENT_ID`: Your Azure AD application client ID
   - `AZURE_CLIENT_SECRET`: Your Azure AD application client secret
   - `AZURE_TENANT_ID`: Your Azure AD tenant ID

3. Local Development:
   - No authentication required
   - All endpoints are accessible without credentials

4. Production (Azure):
   - Users must be authenticated with Azure AD
   - Only users from the same tenant as the application can access the system
   - Users from other tenants will receive a 401 Unauthorized response
   - Any authenticated user from the correct tenant can access all features 