import requests
from bs4 import BeautifulSoup
from tenacity import retry, wait_fixed, stop_after_attempt
from urllib.robotparser import RobotFileParser
from urllib.parse import urljoin, urlparse
import re
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor
from collections import Counter
import os

# Step 1: Web Scraping
@retry(wait=wait_fixed(2), stop=stop_after_attempt(5))
def fetch_website_content(url):
    try:
        response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
        response.raise_for_status()
        print("Website content fetched successfully.")
        return response.content
    except requests.exceptions.RequestException as e:
        print(f"Error fetching the website content: {e}")
        raise

def is_scraping_allowed(url, user_agent='*'):
    parsed_url = requests.utils.urlparse(url)
    base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
    robots_url = f"{base_url}/robots.txt"
    rp = RobotFileParser()
    rp.set_url(robots_url)
    rp.read()
    can_fetch = rp.can_fetch(user_agent, url)
    if can_fetch:
        print("Scraping is allowed by robots.txt")
    else:
        print("Scraping is not allowed by robots.txt")
    return can_fetch

def extract_elements(html_content, base_url):
    soup = BeautifulSoup(html_content, 'html.parser')
    
    css_files = [urljoin(base_url, link.get('href')) for link in soup.find_all('link', rel='stylesheet')]
    print(f"CSS files found: {css_files}")
    
    return {
        'css_files': css_files
    }

# Step 2: Data Processing and Analysis
def fetch_css_content(css_url):
    try:
        response = requests.get(css_url, headers={"User-Agent": "Mozilla/5.0"})
        response.raise_for_status()
        print(f"CSS content fetched from: {css_url}")
        return response.text
    except requests.exceptions.RequestException as e:
        print(f"Error fetching the CSS content from {css_url}: {e}")
        return None

def extract_colors(css_content):
    color_pattern = re.compile(r'#(?:[0-9a-fA-F]{3}){1,2}\b')
    colors = color_pattern.findall(css_content)
    return [expand_color_shorthand(color) for color in colors]

def expand_color_shorthand(color):
    """
    Expand shorthand hex color codes to full six-character format.
    Example: #eee -> #eeeeee, #fff -> #ffffff
    """
    if color.startswith('#') and len(color) == 4:
        return f"#{color[1]*2}{color[2]*2}{color[3]*2}"
    else:
        return color

def get_top_colors(colors, num_colors=5):
    # Filter out common and less meaningful colors
    colors = [color for color in colors if color.lower() not in ['#fff', '#ffffff', '#000', '#000000']]
    color_counter = Counter(colors)
    top_colors = color_counter.most_common(num_colors)
    print(f"Top {num_colors} colors: {top_colors}")
    return [color[0] for color in top_colors]

def extract_button_colors(html_content, css_contents):
    soup = BeautifulSoup(html_content, 'html.parser')
    button_colors = []

    # Extract button colors from inline styles
    buttons = soup.find_all(['button', 'a', 'input'])
    for button in buttons:
        style = button.get('style', '')
        button_colors.extend(re.findall(r'#(?:[0-9a-fA-F]{3}){1,2}\b', style))

    # Extract button colors from CSS
    for css_content in css_contents:
        button_styles = re.findall(r'button\s*{[^}]*}', css_content, re.IGNORECASE)
        for style in button_styles:
            button_colors.extend(re.findall(r'#(?:[0-9a-fA-F]{3}){1,2}\b', style))

    # Remove duplicates
    button_colors = list(set([expand_color_shorthand(color) for color in button_colors]))[:4]
    
    print(f"Button colors extracted: {button_colors}")
    return button_colors

def recommend_contrasting_color(existing_colors):
    # Convert hex color to RGB tuple
    def hex_to_rgb(hex_color):
        hex_color = hex_color.lstrip('#')
        return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))

    # Calculate relative luminance of a color
    def relative_luminance(rgb_color):
        r, g, b = rgb_color
        return 0.2126 * r + 0.7152 * g + 0.0722 * b

    # Find the darkest color in terms of luminance
    rgb_colors = [hex_to_rgb(color) for color in existing_colors]
    sorted_colors = sorted(rgb_colors, key=relative_luminance)
    darkest_color = sorted_colors[0]

    # Define colors of the rainbow (VIBGYOR)
    rainbow_colors = {
        'Violet': '#8a2be2',
        'Indigo': '#4b0082',
        'Blue': '#0000ff',
        'Green': '#00ff00',
        'Yellow': '#ffff00',
        'Orange': '#ffa500',
        'Red': '#ff0000'
    }

    # Choose a contrasting color from rainbow and black/white
    contrast_color = None
    reasons = {}

    for color_name, color_code in rainbow_colors.items():
        rgb_color = hex_to_rgb(color_code)
        luminance_diff = abs(relative_luminance(darkest_color) - relative_luminance(rgb_color))
        if luminance_diff > 0.5:
            contrast_color = color_code
            reasons[contrast_color] = f"{color_name} is a vibrant color that contrasts well with the website's primary colors."

    # Check contrast with white and black
    white = (255, 255, 255)
    black = (0, 0, 0)

    if abs(relative_luminance(darkest_color) - relative_luminance(white)) > 0.5:
        contrast_color = '#ffffff'  # White provides better contrast
        reasons[contrast_color] = "White is a classic choice that ensures high contrast and readability."
    elif abs(relative_luminance(darkest_color) - relative_luminance(black)) > 0.5:
        contrast_color = '#000000'  # Black provides better contrast
        reasons[contrast_color] = "Black is a versatile choice that enhances readability and visual appeal."

    if not contrast_color:
        # If no suitable rainbow or black/white color found, fallback to default
        contrast_color = '#28a745'  # Green as a placeholder or default

    print(f"Recommended contrasting color: {contrast_color}")
    print(f"Reason: {reasons.get(contrast_color, 'Default choice for contrast')}")
    return contrast_color, reasons.get(contrast_color, 'Default choice for contrast')

def recommend_button_color(primary_colors, button_colors):
    # Combine primary colors and button colors
    existing_colors = set(primary_colors)
    
    # Recommend a contrasting color based on existing colors
    recommended_color = recommend_contrasting_color(existing_colors)

    print(f"Recommended button color: {recommended_color}")
    return recommended_color

# Step 3: Download Logo
def download_logo(domain):
    logo_url = f"https://logo.clearbit.com/{domain}"
    logo_path = f"{domain}_logo.png"
    try:
        response = requests.get(logo_url, stream=True)
        if response.status_code == 200:
            with open(logo_path, 'wb') as f:
                for chunk in response.iter_content(1024):
                    f.write(chunk)
            print(f"Logo downloaded: {logo_path}")
            return logo_path
        else:
            print(f"Failed to download logo for {domain}")
            return None
    except Exception as e:
        print(f"Error downloading logo: {e}")
        return None

# Step 4: Generate Branding Guidelines PDF
def create_pdf(domain, logo_path, primary_colors, button_colors, recommended_color, output_path):
    c = canvas.Canvas(output_path, pagesize=A4)
    width, height = A4
    
    # Add the logo
    if logo_path and os.path.exists(logo_path):
        c.drawImage(logo_path, (width - 100) / 2, height - 150, width=100, height=100)
        print(f"Logo added to PDF: {logo_path}")
    
    # Add primary colors
    y_position = height - 200
    c.setFont("Helvetica", 12)
    c.drawString(50, y_position, "Primary Colors:")
    y_position -= 20

    for color in primary_colors:
        try:
            c.setFillColor(HexColor(color))
        except ValueError:
            print(f"Invalid color {color}, using fallback color")
            c.setFillColor(HexColor("#000000"))
        c.rect(50, y_position, 50, 20, fill=1)
        c.setFillColor(HexColor("#000000"))
        c.drawString(110, y_position + 5, color)
        y_position -= 30
        print(f"Color {color} added to PDF.")
    
    # Add button colors
    y_position -= 20
    c.drawString(50, y_position, "Button Colors:")
    y_position -= 20

    for color in button_colors:
        try:
            c.setFillColor(HexColor(color))
        except ValueError:
            print(f"Invalid button color {color}, using fallback color")
            c.setFillColor(HexColor("#000000"))
        c.rect(50, y_position, 50, 20, fill=1)
        c.setFillColor(HexColor("#000000"))
        c.drawString(110, y_position + 5, color)
        y_position -= 30
        print(f"Button color {color} added to PDF.")
    
    # Add recommended button color
    y_position -= 20
    c.drawString(50, y_position, "Recommended Button Color:")
    y_position -= 20

    try:
        c.setFillColor(HexColor(recommended_color[0]))
    except ValueError:
        print(f"Invalid recommended button color {recommended_color}, using fallback color")
        c.setFillColor(HexColor("#000000"))
    c.rect(50, y_position, 50, 20, fill=1)
    c.setFillColor(HexColor("#000000"))
    c.drawString(110, y_position + 5, recommended_color[0])
    print(f"Recommended button color {recommended_color[0]} added to PDF.")

    c.drawString(110, y_position - 20, recommended_color[1])
    
    c.save()
    print(f"Branding guidelines PDF created at: {output_path}")
    return output_path

# Main function to orchestrate scraping and analysis
def scrape_and_analyze(url):
    if is_scraping_allowed(url):
        html_content = fetch_website_content(url)
        if html_content:
            elements = extract_elements(html_content, url)
            all_colors = []
            css_contents = []
            for css_url in elements.get('css_files', []):
                css_content = fetch_css_content(css_url)
                if css_content:
                    all_colors.extend(extract_colors(css_content))
                    css_contents.append(css_content)
            primary_colors = get_top_colors(all_colors, 5)
            button_colors = extract_button_colors(html_content, css_contents)
            recommended_color = recommend_button_color(primary_colors, button_colors)
            parsed_url = urlparse(url)
            domain = parsed_url.netloc
            logo_path = download_logo(domain)
            pdf_path = create_pdf(domain, logo_path, primary_colors, button_colors, recommended_color, "branding_guidelines.pdf")
            return logo_path, primary_colors, button_colors, recommended_color, pdf_path
        else:
            print("Failed to fetch website content.")
            return None, None, None, None, None
    else:
        print("Scraping not allowed by robots.txt")
        return None, None, None, None, None

# Example usage
if __name__ == "__main__":
    url = "https://www.amazon.com"
    logo_path, primary_colors, button_colors, recommended_color, pdf_path = scrape_and_analyze(url)
    
    # Output results
    print(f"Logo Path: {logo_path}")
    print(f"Primary Colors: {primary_colors}")
    print(f"Button Colors: {button_colors}")
    print(f"Recommended Button Color: {recommended_color}")
    print(f"PDF Path: {pdf_path}")
