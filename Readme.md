# Industrial Automation Dashboard

A real-time monitoring and analytics platform for industrial machine performance tracking with ML-powered predictive insights.

## Overview

Industrial Automation Dashboard is a real-time monitoring and analytics platform designed to collect, visualize, and analyze machine performance data. The system helps industries track operational metrics, monitor equipment status, and generate insights for data-driven decision-making.

The project incorporates Machine Learning models to predict machine behavior and identify potential operational issues using historical machine data.

---

## Table of Contents

- [Features](#features)
- [Tech Stack](#tech-stack)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Usage](#usage)
- [Project Structure](#project-structure)
- [System Workflow](#system-workflow)
- [Future Improvements](#future-improvements)
- [Author](#author)

---

## Features

- **Real-Time Monitoring**: Track machine parameters and operational status with live dashboard updates
- **Data Visualization**: Interactive charts and graphs with historical trend analysis
- **Machine Learning Predictions**: Predict machine behavior and detect anomalies for preventive maintenance
- **Analytics & Reporting**: Analyze efficiency and monitor key performance metrics
- **Responsive Interface**: User-friendly dashboard design with easy navigation

---

## Tech Stack

### Frontend
- HTML5
- CSS3
- JavaScript (Chart.js for visualizations)

### Backend
- Python 3.x
- Flask

### Data Processing & ML
- Pandas
- NumPy
- Scikit-learn

---

## Prerequisites

- Python 3.8 or higher
- pip (Python package manager)
- Web browser (Chrome, Firefox, Safari, or Edge)

---

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/ParasBhegade/Industial-automation-dashboard.git
   cd Dashboard
   ```

2. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Run the application:
   ```bash
   python app.py
   ```

5. Open your browser and navigate to:
   ```
   http://localhost:5000
   ```

---

## Usage

1. Access the dashboard through the web interface
2. Navigate to the monitoring section to view real-time machine data
3. Use the analytics section to review historical trends
4. Check predictions for maintenance alerts
5. Generate reports as needed

---

## Project Structure

```
Dashboard/
├── app.py                      # Flask application entry point
├── train_model.py              # ML model training script
├── backend/                    # Backend processing logic
├── models/                     # Trained ML models
├── static/                     # Frontend assets
│   ├── index.html             # Main dashboard page
│   ├── login.html             # Login page
│   ├── register.html          # Registration page
│   ├── analysis.html          # Analysis page
│   ├── logs.html              # Logs page
│   ├── script.js              # Main JavaScript logic
│   ├── style.css              # Main styles
│   ├── theme.css              # Theme configuration
│   └── *.css / *.js           # Individual page styles and scripts
├── Design/                     # Design assets
├── machine_data_*.csv         # Machine data logs
└── Readme.md                  # Project documentation
```

---

## System Workflow

1. Machine data is collected and processed through the backend
2. Data is transmitted to the Flask server for storage and analysis
3. Historical and real-time data are analyzed using Pandas and NumPy
4. Machine Learning models (Scikit-learn) generate behavior predictions
5. Results are visualized on the dashboard in real-time
6. Users monitor performance metrics and make informed operational decisions

---

## Applications

- Industrial Machine Monitoring
- Predictive Maintenance Planning
- Machine Performance Analysis
- Production Efficiency Tracking
- Operational Decision Support
- Equipment Health Monitoring

---

## Future Improvements

- IoT Device Integration for direct data collection
- Advanced Predictive Analytics with deep learning
- Automated Alert System for critical thresholds
- Cloud Deployment (AWS/Azure)
- Multi-Factory Monitoring and Management
- Advanced Anomaly Detection algorithms
- Mobile Application Interface
- Real-time Notifications

---

## Contributing

Contributions are welcome! Please feel free to submit a pull request or open an issue for any bugs or feature requests.

---

## License

This project is open source and available under the MIT License.

---

## Author

**Paras Bhegade**

B.Tech Computer Science Engineering (Artificial Intelligence & Machine Learning)

For more information or inquiries, please contact via GitHub: [ParasBhegade](https://github.com/ParasBhegade)
