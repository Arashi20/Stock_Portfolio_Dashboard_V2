---
applyTo: '**'
---

I am currently working on a (somewhat lightweight) stock reporting tool web application (for personal use ONLY). The main purpose of this application is to perform Discounted Free Cashflow analyses (DCF analyses) on stocks, and to keep track of notes and due diligence insights on certain stocks. The application will have three main pages: a DCF page, a Reports page, and a Wishlist page.

The DCF page will allow me to input various financial metrics and assumptions about a stock, such as:

- Ticker symbol
- (current) Free cash flow 
- Growth rate for the next 5 years (in percentage)
- Growth rate for the 6-10 years (in percentage)
- Terminal growht rate (in percentage)
- Discount rate (in percentage)
- Number of shares outstanding
- Share dilution (in percentage, can be positive, negative or 0)

Based on these inputs, the application will calculate the intrinsic value of the stock using the Discounted Free Cashflow method (python file).

The results will be displayed on the DCF page, showing the calculated intrinsic value per share, as well as a summary of the inputs provided (this result can also be saved to the database for future reference).

-------------------------------------------------------

The Reports page will allow me to add notes and due diligence insights on certain stocks. I can create a new report by:
- Entering the ticker symbol
- Entering the date of the report
- Entering my notes/insights. 
- By directly clicking on "Create Report" from one of the stocks analyzed on the DCF page.

These reports will be saved to the database and can be viewed later for reference.



-------------------------------------------------------

The Wishlist page will allow me to add stocks to my wishlist for future analyses. I can add a stock to the wishlist by entering:

- A ticker symbol
- A desired price target


 The application will then fetch real-time price information for that stock (using Yahoo finance API) and display it on the Wishlist page. From there, I can directly navigate to the DCF page to perform an analysis on that stock or view a report on that stock.

-------------------------------------------------------

The Home page will provide an overview of the application and its features, as well as quick links to the DCF page, Reports page, and Wishlist page.

-------------------------------------------------------

The web application will be built using Flask for the backend and HTML, CSS, and JavaScript for the frontend. The application will be hosted on Railway under the URL: ['amstocks.nl'].

Make sure that the CSS styling is consistent across all pages, and that the user interface is intuitive and user-friendly. Also ensure that the CSS file is modular and easy to maintain (for all screen sizes).

-------------------------------------------------------

