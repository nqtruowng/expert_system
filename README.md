# expert-system

	How to run the project -
	1. Unzip the file.
	2. Go into the unzipped folder, using the cd command in terminal.
	3. Run the file main.py using the command -> python main.py
	4. Follow along the commands that will be given in the program, further.

	Our project is a combination of two types of systems: 
	1. Knowledge based Expert System - It consist of a knowledgs base of the CIA world factbook as 
		offline html files of each countries, which we downloaded from the CIA open source database. 
		This data will be parsed by our system using python beautiful soup package. Anyone can look for the geographical details of any country listed in the system. 
	
	2. Rule based Expert System - It will provide you with suggestions to LIVE, WORK or TRAVEL in 
		different countries. It will give you suggestions based on the options that you choose, 
		by selecting from the worlds top 50 countries based on their GDP. The database of these top 
		50 countries are stored in two files in our project countries.csv and Tourism.csv. This will ensure that the countries that are suggested are the best possible options. 

## Web interface (Flask)

Run a simple web UI instead of the console app:

```
pip install -r requirements.txt
python web_app.py
```

Then open `http://127.0.0.1:5000` in your browser.

- Home: links to all sections
- Countries: list of available countries from `countryList.txt`
- Knowledge Search: select a country and ask for a topic (e.g. `location`, `climate`, `population`). Special commands: `;lst`, `;keys`, `;matches`.
- Expert Suggestions: simple forms for Live/Work/Travel derived from `countries.csv` and `Tourism.csv`.

