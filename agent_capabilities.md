# AI-Powered Menu Scraping Agent - Capabilities Overview

## 🎯 **Primary Mission**
Automatically scrape cannabis dispensary menus, process product data, and maintain an up-to-date inventory database with intelligent error recovery and AI-powered product name generation.

---

## 🚀 **Core Capabilities**

### 1. **Automated Web Scraping**
- **Multi-Platform Support**: Scrapes 9+ dispensary platforms (Dutchie, Leafly, iHeartJane, etc.)
- **Dynamic URL Detection**: Automatically selects appropriate scraper based on store URL
- **Configurable Stores**: Processes 29+ dispensaries from configuration file
- **Product Extraction**: Captures product names, prices, categories, THC levels, availability

### 2. **Intelligent Error Recovery**
- **Real-Time Monitoring**: Watches scraper execution for errors and failures
- **Auto-Diagnosis**: Identifies common issues (missing imports, package failures, browser crashes)
- **Automatic Fixes**: 
  - Adds missing import statements
  - Installs missing Python packages via pip
  - Retries failed requests
  - Handles browser crashes gracefully
- **Claude AI Integration**: Uses AI to analyze and fix complex, unfamiliar errors
- **Safe Deployment**: Creates backups before applying any code changes

### 3. **AI-Powered Product Intelligence**
- **Internal Name Generation**: Creates canonical internal product names using Claude AI
- **Quality Validation**: Multi-factor scoring system for generated names
- **Brand Filtering**: Automatically removes brand names from product names
- **Duplicate Prevention**: Checks against existing patterns before creating new ones
- **Pattern Learning**: Builds and extends internal product name library automatically

### 4. **Data Processing & Normalization**
- **Product Validation**: Ensures data quality and consistency
- **Price Formatting**: Standardizes price structures across dispensaries
- **Tax Calculation**: Applies appropriate tax rates
- **Category Mapping**: Normalizes product categories
- **SKU Generation**: Creates unique product identifiers
- **Change Detection**: Compares daily data against previous day's inventory

### 5. **Database Management**
- **JSON Storage**: Maintains historical data in structured JSON files
- **Date-Based Organization**: Stores products by date for tracking trends
- **Incremental Updates**: Only processes new or changed products
- **Data Integrity**: Validates and cleans incoming product data

### 6. **Notification & Reporting**
- **Email Alerts**: Sends daily reports on scraping results
- **Change Notifications**: Alerts team to inventory changes
- **AI Mapping Alerts**: Notifies when new AI-generated product names are created
- **Error Reports**: Detailed error information with fix attempts
- **Success Metrics**: Tracks scraping performance and statistics

---

## 🔄 **Daily Workflow**

### **Phase 1: Initialization**
```
Load Configuration → Setup Logging → Initialize Data Processor → Track Metrics
```

### **Phase 2: Scraping Loop**
```
For Each Store:
  ├─ Select Appropriate Scraper (Dutchie/Leafly/etc.)
  ├─ Execute Product Extraction
  ├─ Validate & Normalize Data
  ├─ Generate Internal Names (AI if needed)
  └─ Store Results
```

### **Phase 3: Post-Processing**
```
Compare with Yesterday → Generate Reports → Upload to Drive → Send Notifications
```

---

## 🛡️ **Safety & Reliability Features**

### **Error Handling**
- **Graceful Degradation**: Continues processing other stores if one fails
- **Retry Logic**: Up to 3 attempts with exponential backoff
- **Timeout Protection**: Prevents infinite hangs
- **Resource Cleanup**: Properly closes browsers and connections

### **Data Protection**
- **Backup System**: Automatic backups before any code modifications
- **Audit Trail**: Complete log of all AI decisions and changes
- **Append-Only**: Never modifies existing internal product names
- **Validation Gates**: Multiple quality checkpoints before data acceptance

### **Performance Optimization**
- **Concurrent Processing**: Processes multiple stores in parallel
- **Caching**: Avoids redundant API calls and data processing
- **Memory Management**: Efficient handling of large product datasets
- **Network Optimization**: Connection pooling and request batching

---

## 🤖 **AI Agent Intelligence**

### **Product Name Generation**
- **Context Understanding**: Analyzes product names to extract core strain names
- **Brand Removal**: Automatically filters out brand names (Rhize, Kiva, etc.)
- **Format Standardization**: Ensures consistent title case formatting
- **Quality Scoring**: Evaluates names based on strain indicators and patterns

### **Error Resolution**
- **Pattern Recognition**: Identifies common error types from logs
- **Code Analysis**: Understands Python syntax and structure
- **Targeted Fixes**: Generates precise code patches for specific issues
- **Validation**: Tests fixes before deployment

---

## 📊 **Data Output & Integration**

### **Product Data Structure**
```json
{
  "Product name": "Animal Face 1g Pre Roll",
  "Category": "Pre-Roll", 
  "Brand": "Rhize Cannabis Company",
  "Price": {"1g": "$16.80"},
  "THC": "N/A",
  "Internal Product Name": "Animal Face",
  "Internal Product Type": "Pre-Roll",
  "SKU": "animal-face-pre-roll-1g"
}
```

### **Historical Tracking**
- **Daily Snapshots**: Complete inventory for each day
- **Change Detection**: Identifies new, removed, and modified products
- **Trend Analysis**: Tracks price changes and availability patterns
- **Performance Metrics**: Monitors scraping success rates

---

## 🎛️ **Configuration & Control**

### **Store Configuration**
- **Dynamic Settings**: Each store has customizable parameters
- **Brand Filtering**: Specific brand targeting per store
- **Category Selection**: Optional category filtering
- **Tax Rates**: Store-specific tax calculations

### **Agent Settings**
- **Retry Limits**: Configurable retry attempts
- **API Integration**: Claude API model selection
- **Notification Preferences**: Email routing and content
- **Performance Tuning**: Timeout and concurrency settings

---

## 📈 **Business Value**

### **Operational Efficiency**
- **Automation**: Eliminates manual data entry and monitoring
- **Reliability**: 24/7 operation with automatic error recovery
- **Scalability**: Easily add new dispensaries and platforms
- **Consistency**: Standardized data across all sources

### **Data Intelligence**
- **Real-Time Updates**: Current inventory status across all locations
- **Market Insights**: Pricing trends and product availability
- **Quality Assurance**: AI-powered data validation and normalization
- **Historical Analysis**: Complete product and pricing history

### **Cost Savings**
- **Reduced Labor**: Minimal human intervention required
- **Error Prevention**: Proactive issue detection and resolution
- **Efficient Resource Use**: Optimized scraping and processing
- **Scalable Architecture**: Handles growth without proportional cost increase

---

## 🔮 **Future Capabilities**

### **Planned Enhancements**
- **Predictive Analytics**: Forecast inventory needs and pricing trends
- **Competitive Intelligence**: Market analysis across dispensaries
- **API Integration**: Direct dispensary API connections where available
- **Mobile Dashboard**: Real-time monitoring and control interface

### **Advanced AI Features**
- **Product Recommendations**: Suggest similar products across stores
- **Price Optimization**: Identify best deals and pricing opportunities
- **Inventory Alerts**: Notify about stock changes and availability
- **Market Analysis**: Automated reporting on market conditions

---

This agent transforms manual dispensary monitoring into an automated, intelligent system that not only collects data but actively improves itself through AI-powered learning and error recovery.
