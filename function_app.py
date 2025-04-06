import os
import azure.functions as func
import logging
import pyodbc
import json
from azure.identity import ClientSecretCredential
from dotenv import load_dotenv
from functools import wraps
import threading

# Load environment variables
load_dotenv()

# Azure AD credentials
client_id = os.getenv('AZURE_CLIENT_ID')
client_secret = os.getenv('AZURE_CLIENT_SECRET')
tenant_id = os.getenv('AZURE_TENANT_ID')

# SQL Server details
server = os.getenv('SQL_SERVER')
database = os.getenv('SQL_DATABASE')
port = os.getenv('SQL_PORT')

# Check if running in Azure
is_azure = os.getenv('WEBSITE_INSTANCE_ID') is not None

# Connection pool
_connection_pool = {}
_connection_pool_lock = threading.Lock()

def get_db_connection():
    """Get a database connection from the pool or create a new one"""
    thread_id = threading.get_ident()
    
    with _connection_pool_lock:
        if thread_id in _connection_pool:
            try:
                # Test if connection is still alive
                _connection_pool[thread_id].cursor().execute("SELECT 1")
                return _connection_pool[thread_id]
            except:
                # Connection is dead, remove it
                del _connection_pool[thread_id]
        
        # Create new connection
        token = get_access_token()
        connection_string = (
            f"Driver={{ODBC Driver 17 for SQL Server}};"
            f"Server=tcp:{server},{port};"
            f"Database={database};"
            "Encrypt=yes;"
            "TrustServerCertificate=no;"
            "Connection Timeout=30;"
            "Authentication=ActiveDirectoryServicePrincipal;"
            f"UID={client_id}@{tenant_id};"
            f"PWD={client_secret};"
        )
        
        conn = pyodbc.connect(connection_string)
        _connection_pool[thread_id] = conn
        return conn

def require_auth(f):
    """Decorator to handle authentication"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        req = args[0]
        is_authenticated, error_message = check_authentication(req)
        if not is_authenticated:
            return func.HttpResponse(error_message, status_code=401)
        return f(*args, **kwargs)
    return decorated_function

def format_response(data, status_code=200):
    """Helper function to format consistent responses"""
    return func.HttpResponse(
        json.dumps(data, default=str),
        mimetype="application/json",
        status_code=status_code
    )

# Cache for schema
_schema_cache = None
_schema_cache_lock = threading.Lock()

def get_cached_schema():
    """Get schema from cache or fetch from database"""
    global _schema_cache
    
    with _schema_cache_lock:
        if _schema_cache is None:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT 
                    c.COLUMN_NAME,
                    c.DATA_TYPE,
                    c.CHARACTER_MAXIMUM_LENGTH,
                    c.IS_NULLABLE,
                    COLUMNPROPERTY(OBJECT_ID('StationTracking'), c.COLUMN_NAME, 'IsIdentity') as IS_IDENTITY,
                    CASE 
                        WHEN c.DATA_TYPE = 'bit' THEN 'bit'
                        WHEN c.DATA_TYPE IN ('int', 'bigint', 'smallint', 'tinyint') THEN 'number'
                        ELSE 'text'
                    END as INPUT_TYPE
                FROM INFORMATION_SCHEMA.COLUMNS c
                WHERE c.TABLE_NAME = 'StationTracking'
                ORDER BY c.ORDINAL_POSITION
            """)
            
            columns = []
            for row in cursor.fetchall():
                column = {
                    'name': row[0],
                    'type': row[1],
                    'max_length': row[2],
                    'is_nullable': row[3] == 'YES',
                    'is_identity': bool(row[4]),
                    'input_type': row[5]
                }
                columns.append(column)
            
            _schema_cache = columns
        
        return _schema_cache

def check_authentication(req: func.HttpRequest) -> tuple[bool, str]:
    """Check if the request is authenticated and from the correct tenant"""
    if not is_azure:
        return True, ""
    
    # Get the client principal from the request headers
    client_principal_id = req.headers.get('X-MS-CLIENT-PRINCIPAL-ID')
    client_principal_name = req.headers.get('X-MS-CLIENT-PRINCIPAL-NAME')
    client_principal_tenant_id = req.headers.get('X-MS-CLIENT-PRINCIPAL-TENANT-ID')
    
    if not client_principal_id:
        return False, "Unauthorized - Please log in to access this application"
    
    if client_principal_tenant_id != tenant_id:
        return False, f"Unauthorized - Only users from tenant {tenant_id} are allowed to access this application"
    
    return True, ""

def get_access_token():
    """Get access token using service principal credentials"""
    credential = ClientSecretCredential(
        tenant_id=tenant_id,
        client_id=client_id,
        client_secret=client_secret
    )
    
    # Get token for SQL Server resource
    access_token = credential.get_token("https://database.windows.net/.default")
    return access_token.token

# Set auth level based on environment
auth_level = func.AuthLevel.ANONYMOUS if not is_azure else func.AuthLevel.FUNCTION

app = func.FunctionApp(http_auth_level=auth_level)

@app.route(route="ui", methods=["GET"])
def serve_ui(req: func.HttpRequest) -> func.HttpResponse:
    # Check authentication
    is_authenticated, error_message = check_authentication(req)
    if not is_authenticated:
        return func.HttpResponse(error_message, status_code=401)

    html_content = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Weather Station Configuration</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdn.jsdelivr.net/npm/toastify-js/src/toastify.min.css" rel="stylesheet">
    <link href="https://cdn.jsdelivr.net/npm/@fortawesome/fontawesome-free/css/all.min.css" rel="stylesheet">
    <style>
        :root {
            --fabric-primary: #0078D4;
            --fabric-bg: #FAF9F8;
            --fabric-text: #323130;
            --fabric-border: #EDEBE9;
        }
        
        body {
            font-family: 'Segoe UI', sans-serif;
            background-color: var(--fabric-bg);
            color: var(--fabric-text);
        }

        .navbar {
            background-color: var(--fabric-primary);
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }

        .table {
            background-color: white;
            border-radius: 4px;
            box-shadow: 0 1px 4px rgba(0,0,0,0.1);
        }

        .table thead th {
            background-color: #F8F8F8;
            border-bottom: 2px solid var(--fabric-border);
            color: #605E5C;
            font-weight: 600;
        }

        .table td {
            vertical-align: middle;
            padding: 12px;
            border-bottom: 1px solid var(--fabric-border);
        }

        .btn-primary {
            background-color: var(--fabric-primary);
            border-color: var(--fabric-primary);
        }

        .btn-primary:hover {
            background-color: #106EBE;
            border-color: #106EBE;
        }

        .action-buttons .btn {
            padding: 4px 8px;
            margin: 0 2px;
        }

        .form-check-input:checked {
            background-color: var(--fabric-primary);
            border-color: var(--fabric-primary);
        }

        .modal-content {
            border-radius: 4px;
            box-shadow: 0 4px 8px rgba(0,0,0,0.1);
        }

        .modal-header {
            background-color: #F8F8F8;
            border-bottom: 1px solid var(--fabric-border);
        }

        .loading {
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(255, 255, 255, 0.8);
            display: none;
            justify-content: center;
            align-items: center;
            z-index: 1000;
        }

        .loading .spinner-border {
            color: var(--fabric-primary);
        }

        .command-bar {
            background-color: white;
            padding: 16px;
            margin-bottom: 20px;
            border-radius: 4px;
            box-shadow: 0 1px 4px rgba(0,0,0,0.1);
        }

        .sortable {
            cursor: pointer;
            user-select: none;
        }
        .sortable:hover {
            background-color: #F0F0F0;
        }
        .sort-icon {
            display: inline-block;
            width: 0;
            height: 0;
            margin-left: 8px;
            vertical-align: middle;
        }
        .sort-asc .sort-icon {
            border-left: 4px solid transparent;
            border-right: 4px solid transparent;
            border-bottom: 4px solid #666;
        }
        .sort-desc .sort-icon {
            border-left: 4px solid transparent;
            border-right: 4px solid transparent;
            border-top: 4px solid #666;
        }
    </style>
</head>
<body>
    <div class="loading">
        <div class="spinner-border" role="status">
            <span class="visually-hidden">Loading...</span>
        </div>
    </div>

    <nav class="navbar navbar-dark">
        <div class="container">
            <span class="navbar-brand">Weather Station Configuration</span>
        </div>
    </nav>

    <div class="container mt-4">
        <div class="command-bar">
            <button class="btn btn-primary" onclick="showAddStationModal()">
                <i class="fas fa-plus"></i> Add New Station
            </button>
        </div>

        <div class="table-responsive">
            <table class="table">
                <thead>
                    <tr id="stationsTableHeader">
                        <!-- Headers will be dynamically added here -->
                    </tr>
                </thead>
                <tbody id="stationsTableBody">
                    <!-- Stations will be dynamically added here -->
                </tbody>
            </table>
        </div>
    </div>

    <!-- Add/Edit Station Modal -->
    <div class="modal fade" id="stationModal" tabindex="-1">
        <div class="modal-dialog">
            <div class="modal-content">
                <div class="modal-header">
                    <h5 class="modal-title" id="modalTitle">Add Station</h5>
                    <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                </div>
                <div class="modal-body">
                    <form id="stationForm">
                        <!-- Form fields will be dynamically added here -->
                    </form>
                </div>
                <div class="modal-footer">
                    <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cancel</button>
                    <button type="button" class="btn btn-primary" onclick="saveStation()">Save</button>
                </div>
            </div>
        </div>
    </div>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/toastify-js"></script>
    <script>
        let schema = [];
        let stations = [];
        let currentStation = null;
        let stationModal;
        let baseUrl = window.location.origin;
        let currentSort = { column: null, ascending: true };

        document.addEventListener('DOMContentLoaded', async function() {
            try {
                // Initialize the modal when the DOM is loaded
                stationModal = new bootstrap.Modal(document.getElementById('stationModal'));
                // Initialize the application
                await initialize();
            } catch (error) {
                console.error('Failed to initialize:', error);
                showToast('Failed to initialize application: ' + error.message, 'error');
            }
        });

        function showLoading() {
            document.querySelector('.loading').style.display = 'flex';
        }

        function hideLoading() {
            document.querySelector('.loading').style.display = 'none';
        }

        function showToast(message, type = 'success') {
            Toastify({
                text: message,
                duration: 3000,
                gravity: "top",
                position: "right",
                style: {
                    background: type === 'success' ? "#107C10" : "#A4262C"
                }
            }).showToast();
        }

        async function initialize() {
            try {
                showLoading();
                const schemaResponse = await fetch(`${baseUrl}/api/schema`);
                if (!schemaResponse.ok) {
                    throw new Error('Failed to fetch schema');
                }
                const schemaData = await schemaResponse.json();
                schema = schemaData.columns;
                await loadStations();
            } catch (error) {
                console.error('Initialization error:', error);
                throw error;
            } finally {
                hideLoading();
            }
        }

        async function loadStations() {
            try {
                const response = await fetch(`${baseUrl}/api/stations`);
                const data = await response.json();
                stations = data.stations;
                renderStationsTable();
            } catch (error) {
                console.error('Error loading stations:', error);
                showToast('Failed to load stations', 'error');
            }
        }

        function formatLabel(columnName) {
            // Special cases
            if (columnName === 'URL') return 'URL';
            if (columnName === 'isActive') return 'Active';
            if (columnName === 'stationID') return 'Station ID';
            
            // Add spaces before capital letters and capitalize first letter
            return columnName
                .replace(/([A-Z])/g, ' $1') // Add space before capital letters
                .replace(/^./, str => str.toUpperCase()) // Capitalize first letter
                .replace('Station I D', 'Station ID') // Fix Station ID formatting
                .trim(); // Remove any leading/trailing spaces
        }

        function sortStations(column) {
            if (currentSort.column === column) {
                // If clicking the same column, reverse the sort direction
                currentSort.ascending = !currentSort.ascending;
            } else {
                // New column, set it as the sort column in ascending order
                currentSort.column = column;
                currentSort.ascending = true;
            }

            stations.sort((a, b) => {
                let valueA = a[column];
                let valueB = b[column];

                // Handle null values
                if (valueA === null || valueA === undefined) return 1;
                if (valueB === null || valueB === undefined) return -1;

                // Convert to lowercase for string comparison
                if (typeof valueA === 'string') valueA = valueA.toLowerCase();
                if (typeof valueB === 'string') valueB = valueB.toLowerCase();

                if (valueA < valueB) return currentSort.ascending ? -1 : 1;
                if (valueA > valueB) return currentSort.ascending ? 1 : -1;
                return 0;
            });

            renderStationsTable();
        }

        function renderStationsTable() {
            // Render headers first
            const thead = document.getElementById('stationsTableHeader');
            const columnHeaders = schema
                .filter(col => !col.name.includes('ConnectionString') && 
                             col.name !== 'ID' && 
                             col.name !== 'TempestToken')
                .map(col => {
                    const isSortColumn = currentSort.column === col.name;
                    const sortClass = isSortColumn 
                        ? (currentSort.ascending ? 'sort-asc' : 'sort-desc')
                        : '';
                    
                    if (col.name === 'IsActive') {
                        return `
                            <th class="sortable ${sortClass}" onclick="sortStations('${col.name}')">
                                Active
                                <span class="sort-icon"></span>
                            </th>`;
                    }
                    return `
                        <th class="sortable ${sortClass}" onclick="sortStations('${col.name}')">
                            ${formatLabel(col.name)}
                            <span class="sort-icon"></span>
                        </th>`;
                })
                .join('');
            thead.innerHTML = columnHeaders + '<th>Actions</th>';

            // Render table body
            const tbody = document.getElementById('stationsTableBody');
            tbody.innerHTML = stations.map(station => {
                const cells = schema
                    .filter(col => !col.name.includes('ConnectionString') && 
                                 col.name !== 'ID' && 
                                 col.name !== 'TempestToken')
                    .map(col => {
                        if (col.type === 'bit' || col.name === 'IsActive') {
                            return `
                                <td class="text-center">
                                    <div class="form-check d-flex justify-content-center">
                                        <input class="form-check-input" 
                                               type="checkbox" 
                                               ${station.IsActive ? 'checked' : ''} 
                                               disabled>
                                    </div>
                                </td>`;
                        }
                        return `<td>${station[col.name] || ''}</td>`;
                    })
                    .join('');

                return `
                    <tr>
                        ${cells}
                        <td class="action-buttons">
                            <button class="btn btn-sm btn-outline-primary" onclick="editStation(${station.ID})" title="Edit">
                                <i class="fas fa-edit"></i>
                            </button>
                            <button class="btn btn-sm btn-outline-secondary" onclick="cloneStation(${station.ID})" title="Clone">
                                <i class="fas fa-clone"></i>
                            </button>
                            <button class="btn btn-sm btn-outline-danger" onclick="deleteStation(${station.ID})" title="Delete">
                                <i class="fas fa-trash"></i>
                            </button>
                        </td>
                    </tr>`;
            }).join('');
        }

        function showAddStationModal() {
            currentStation = null;
            document.getElementById('modalTitle').textContent = 'Add Station';
            renderForm({});
            stationModal.show();
        }

        function editStation(id) {
            currentStation = stations.find(s => s.ID === id);
            document.getElementById('modalTitle').textContent = 'Edit Station';
            renderForm(currentStation);
            stationModal.show();
        }

        function renderForm(data) {
            const form = document.getElementById('stationForm');
            form.innerHTML = schema
                .filter(col => col.name !== 'ID')
                .map(col => {
                    // Handle boolean type (isActive)
                    if (col.type === 'bit' || col.name === 'IsActive') {
                        // For new station (data is empty), default to checked
                        const isChecked = Object.keys(data).length === 0 ? true : data.IsActive;
                        return `
                            <div class="mb-3">
                                <div class="form-check">
                                    <input type="checkbox" 
                                           class="form-check-input" 
                                           id="isActive" 
                                           name="isActive" 
                                           ${isChecked ? 'checked' : ''}>
                                    <label class="form-check-label" for="isActive">Active</label>
                                </div>
                            </div>`;
                    }
                    
                    // Handle integer type (stationID)
                    if (col.name === 'stationID') {
                        return `
                            <div class="mb-3">
                                <label class="form-label">Station ID</label>
                                <input type="number" 
                                       class="form-control" 
                                       name="${col.name}" 
                                       value="${data[col.name] || ''}"
                                       ${col.is_nullable ? '' : 'required'}>
                            </div>`;
                    }

                    // Default text input for other fields
                    return `
                        <div class="mb-3">
                            <label class="form-label">${formatLabel(col.name)}</label>
                            <input type="text" 
                                   class="form-control" 
                                   name="${col.name}" 
                                   value="${data[col.name] || ''}"
                                   ${col.is_nullable ? '' : 'required'}>
                        </div>`;
                }).join('');
        }

        async function saveStation() {
            try {
                showLoading();
                const formData = new FormData(document.getElementById('stationForm'));
                const data = Object.fromEntries(formData);
                
                // Convert checkbox value to boolean and ensure correct case
                data.IsActive = formData.get('isActive') === 'on';
                delete data.isActive;  // Remove lowercase version
                
                // Convert stationID to number if present
                if (data.stationID) {
                    data.stationID = parseInt(data.stationID, 10);
                }

                const url = currentStation
                    ? `${baseUrl}/api/stations/${currentStation.ID}`
                    : `${baseUrl}/api/stations`;

                const response = await fetch(url, {
                    method: currentStation ? 'PUT' : 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(data)
                });

                if (response.ok) {
                    // First hide the modal
                    stationModal.hide();
                    
                    // Then reload the data
                    await loadStations();
                    
                    // Finally show the success message
                    showToast(`Station ${currentStation ? 'updated' : 'created'} successfully`);
                } else {
                    const errorData = await response.json();
                    throw new Error(errorData.error || 'Failed to save station');
                }
            } catch (error) {
                console.error('Error saving station:', error);
                showToast('Failed to save station: ' + error.message, 'error');
            } finally {
                hideLoading();
            }
        }

        async function cloneStation(id) {
            if (!confirm('Are you sure you want to clone this station?')) return;

            try {
                showLoading();
                const response = await fetch(`${baseUrl}/api/stations/clone/${id}`, {
                    method: 'POST'
                });

                if (response.ok) {
                    await loadStations();
                    showToast('Station cloned successfully');
                } else {
                    throw new Error('Failed to clone station');
                }
            } catch (error) {
                console.error('Error cloning station:', error);
                showToast('Failed to clone station', 'error');
            } finally {
                hideLoading();
            }
        }

        async function deleteStation(id) {
            if (!confirm('Are you sure you want to delete this station?')) return;

            try {
                showLoading();
                const response = await fetch(`${baseUrl}/api/stations/${id}`, {
                    method: 'DELETE'
                });

                if (response.ok) {
                    await loadStations();
                    showToast('Station deleted successfully');
                } else {
                    throw new Error('Failed to delete station');
                }
            } catch (error) {
                console.error('Error deleting station:', error);
                showToast('Failed to delete station', 'error');
            } finally {
                hideLoading();
            }
        }
    </script>
</body>
</html>
    """
    
    return func.HttpResponse(
        html_content,
        mimetype="text/html",
        status_code=200
    )

@app.route(route="schema", auth_level=auth_level)
@require_auth
def get_schema(req: func.HttpRequest) -> func.HttpResponse:
    try:
        schema = get_cached_schema()
        return format_response({"columns": schema})
    except Exception as e:
        logging.error(f"Error getting schema: {str(e)}")
        return format_response({"error": str(e)}, 500)

@app.route(route="stations", methods=["GET"], auth_level=auth_level)
@require_auth
def get_stations(req: func.HttpRequest) -> func.HttpResponse:
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM StationTracking")
        columns = [column[0] for column in cursor.description]
        
        stations = []
        for row in cursor.fetchall():
            station = dict(zip(columns, row))
            stations.append(station)
        
        return format_response({"stations": stations})
    except Exception as e:
        logging.error(f"Error getting stations: {str(e)}")
        return format_response({"error": str(e)}, 500)

@app.route(route="stations", methods=["POST"], auth_level=auth_level)
@require_auth
def create_station(req: func.HttpRequest) -> func.HttpResponse:
    try:
        req_body = req.get_json()
        if not req_body:
            raise ValueError("Request body is empty")

        if 'ID' in req_body:
            del req_body['ID']

        if 'IsActive' in req_body:
            req_body['IsActive'] = bool(req_body['IsActive'])
        else:
            req_body['IsActive'] = True

        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            columns = ', '.join(req_body.keys())
            values = ', '.join(['?' for _ in req_body])
            sql = f"INSERT INTO StationTracking ({columns}) OUTPUT INSERTED.* VALUES ({values})"

            cursor.execute(sql, list(req_body.values()))
            row = cursor.fetchone()
            
            if not row:
                raise Exception("Failed to retrieve newly created station")

            columns = [column[0] for column in cursor.description]
            new_station = dict(zip(columns, row))

            conn.commit()
            return format_response({"station": new_station}, 201)
        finally:
            cursor.close()

    except Exception as e:
        logging.error(f"Error creating station: {str(e)}")
        return format_response({"error": str(e)}, 500)

@app.route(route="stations/{id}", methods=["PUT"], auth_level=auth_level)
@require_auth
def update_station(req: func.HttpRequest) -> func.HttpResponse:
    try:
        station_id = req.route_params.get('id')
        req_body = req.get_json()
        
        if 'ID' in req_body:
            del req_body['ID']
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        set_clause = ', '.join([f"{k} = ?" for k in req_body.keys()])
        sql = f"UPDATE StationTracking SET {set_clause} WHERE ID = ?"
        
        params = list(req_body.values()) + [station_id]
        cursor.execute(sql, params)
        conn.commit()
        
        cursor.execute("SELECT * FROM StationTracking WHERE ID = ?", station_id)
        columns = [column[0] for column in cursor.description]
        updated_station = dict(zip(columns, cursor.fetchone()))
        
        return format_response({"station": updated_station})
    except Exception as e:
        logging.error(f"Error updating station: {str(e)}")
        return format_response({"error": str(e)}, 500)

@app.route(route="stations/{id}", methods=["DELETE"], auth_level=auth_level)
@require_auth
def delete_station(req: func.HttpRequest) -> func.HttpResponse:
    try:
        station_id = req.route_params.get('id')
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM StationTracking WHERE ID = ?", station_id)
        conn.commit()
        
        return func.HttpResponse(status_code=204)
    except Exception as e:
        logging.error(f"Error deleting station: {str(e)}")
        return format_response({"error": str(e)}, 500)

@app.route(route="stations/clone/{id}", methods=["POST"], auth_level=auth_level)
@require_auth
def clone_station(req: func.HttpRequest) -> func.HttpResponse:
    try:
        station_id = req.route_params.get('id')
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM StationTracking WHERE ID = ?", station_id)
        columns = [column[0] for column in cursor.description]
        source_station = dict(zip(columns, cursor.fetchone()))
        
        del source_station['ID']
        
        columns = ', '.join(source_station.keys())
        values = ', '.join(['?' for _ in source_station])
        sql = f"INSERT INTO StationTracking ({columns}) VALUES ({values})"
        
        cursor.execute(sql, list(source_station.values()))
        conn.commit()
        
        cursor.execute("SELECT * FROM StationTracking WHERE ID = SCOPE_IDENTITY()")
        new_station = dict(zip(columns.split(','), cursor.fetchone()))
        
        return format_response({"station": new_station}, 201)
    except Exception as e:
        logging.error(f"Error cloning station: {str(e)}")
        return format_response({"error": str(e)}, 500)