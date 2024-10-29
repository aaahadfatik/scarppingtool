import time
from asyncio import timeout

import gspread
from oauth2client.service_account import ServiceAccountCredentials
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager

# Connect to Google Sheets
def connect_to_google_sheets(sheet_url):
    try:
        print(f"Connecting to Google Sheets using URL: {sheet_url}")
        spreadsheet_id = sheet_url.split("/d/")[1].split("/")[0]
        # print(f"Extracted spreadsheet ID: {spreadsheet_id}")
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name('credentials.json', scope)
        client = gspread.authorize(creds)

        # Open the spreadsheet using the extracted ID
        sheet = client.open_by_key(spreadsheet_id).sheet1
        return sheet
    except IndexError:
        print("The provided Google Sheets URL is not in the expected format. Please check the URL.")
        raise

# LinkedIn login function
def linkedin_login(driver, username, password):
    driver.get("https://www.linkedin.com/login")
    WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "username")))

    username_input = driver.find_element(By.ID, "username")
    password_input = driver.find_element(By.ID, "password")

    username_input.send_keys(username)
    password_input.send_keys(password)
    password_input.send_keys(Keys.RETURN)

    WebDriverWait(driver, 20).until(EC.url_contains("feed"))
    print("Login successful.")

# Search LinkedIn for profiles
def search_linkedin(driver, designation, country):
    search_query = f"{designation} in {country}"
    print(f"Searching for: {search_query}")
    driver.get(f"https://www.linkedin.com/search/results/people/?keywords={search_query}")

    profile_urls = set()  # To avoid duplicates
    try:
        # Wait for search results to load
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, ".reusable-search__entity-result-list")))
        print("Search results loaded successfully.")

        # Collect profile URLs
        while True:
            user_links = driver.find_elements(By.CSS_SELECTOR, "a.app-aware-link")
            for link in user_links:
                url = link.get_attribute("href")
                if url and "/in/" in url:  # Only LinkedIn profile links
                    profile_urls.add(url)

            # Click 'Next' button if exists
            try:
                next_button = driver.find_element(By.CSS_SELECTOR, "button[aria-label='Next']")
                next_button.click()
                WebDriverWait(driver, 5).until(EC.staleness_of(next_button))
            except NoSuchElementException:
                break  # Exit loop if no next button

    except TimeoutException:
        print("Timed out waiting for search results to load.")

    return list(profile_urls)

# Wait for profile to load
def wait_for_profile(driver):
    try:
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".pv-text-details__left-panel"))
        )
        print("Profile page loaded.")
    except TimeoutException:
        print("Timed out waiting for the profile page to load.")

# Extract user details from LinkedIn profile
def extract_user_details(driver):
    try:
        name = driver.find_element(By.CSS_SELECTOR,
                                   "h1.text-heading-xlarge.inline.t-24.v-align-middle.break-words").text
    except NoSuchElementException:
        name = "N/A"

    try:
        company = driver.find_element(By.CSS_SELECTOR,
                                      "button[aria-label^='Current company:'] span.text-body-small").text
    except NoSuchElementException:
        company = "N/A"

    try:
        designation = driver.find_element(By.CSS_SELECTOR, "div.text-body-medium.break-words").text
    except NoSuchElementException:
        designation = "N/A"

    # Initialize variables for contact info
    email = "N/A"
    phone = "N/A"
    website = "N/A"
    address = "N/A"
    # Wait and click on the Contact Info link
    try:
        contact_info_link = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "a#top-card-text-details-contact-info"))
        )
        contact_info_link.click()

        # Wait for the contact info section to load by waiting for the email or phone element
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "section.pv-contact-info__contact-type"))
            )

            # Get all the contact type sections
            contact_sections = driver.find_elements(By.CSS_SELECTOR, "section.pv-contact-info__contact-type")

            for section in contact_sections:
                header = section.find_element(By.TAG_NAME, "h3").text.strip()

                if "Email" in header:
                    try:
                        email = section.find_element(By.CSS_SELECTOR, "a[href^='mailto:']").text
                    except NoSuchElementException:
                        email = "N/A"

                elif "Phone" in header:
                    try:
                        phone = section.find_element(By.CSS_SELECTOR, "span.t-black").text
                    except NoSuchElementException:
                        phone = "N/A"

                elif "Website" in header:
                    try:
                        website = section.find_element(By.CSS_SELECTOR, "a[href^='http']").text
                    except NoSuchElementException:
                        website = "N/A"

                elif "Address" in header:
                    try:
                        address = section.find_element(By.CSS_SELECTOR, "span.t-black").text
                    except NoSuchElementException:
                        address = "N/A"

            # Extract email and phone after confirming that the section is loaded
            # try:
            #     email = driver.find_element(By.CSS_SELECTOR,
            #                                 "section.pv-contact-info__contact-type a[href^='mailto:']").text
            # except NoSuchElementException:
            #     email = "N/A"
            #
            # try:
            #     phone = driver.find_element(By.CSS_SELECTOR, "section.pv-contact-info__contact-type span.t-black").text
            # except NoSuchElementException:
            #     phone = "N/A"

        except TimeoutException:
            print("Timed out waiting for the contact info section to load.")

    except TimeoutException:
        print("Contact info link not found or clickable.")
        return name, email, company, designation, phone, website, address
    return name, email, company, designation, phone, website, address

# Extract and save details for multiple profiles
def extract_user_details_from_profiles(driver, profile_urls, sheet):
    user_details_list = []

    for profile_url in profile_urls:
        driver.get(profile_url)
        wait_for_profile(driver)
        time.sleep(2)

        try:
            # Extract details and add them to Google Sheets
            name, email, company, designation, phone, website, address = extract_user_details(driver)
            user_details = {"Name": name, "Email": email, "Company": company, "Designation": designation,
                            "Phone": phone,"website":website,"address":address}
            user_details_list.append(user_details)

            # Append the details to Google Sheets
            sheet.append_row([name, email, company, designation, phone,website,address])
            # print(f"Saved details for {name}: {user_details}")

        except Exception as e:
            print(f"Failed to extract details from {profile_url}: {e}")

    return user_details_list

# Main function
def main(designation, country, google_sheet_url, username, password):
    sheet = connect_to_google_sheets(google_sheet_url)

    # Set up Selenium driver
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()))
    try:
        linkedin_login(driver, username, password)
        time.sleep(5)

        # Search LinkedIn profiles
        profile_urls = search_linkedin(driver, designation, country)
        extract_user_details_from_profiles(driver, profile_urls, sheet)

    finally:
        driver.quit()

# Run main
if __name__ == "__main__":
    SHEET_URL = ""
    # linkedIn credentials
    USERNAME = ""
    PASSWORD = ""
    # linkedIn search
    DESIGNATION = ""
    COUNTRY = ""

    main(DESIGNATION, COUNTRY, SHEET_URL, USERNAME, PASSWORD)
