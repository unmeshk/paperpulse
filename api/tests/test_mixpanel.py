import pytest
import os
import re
import yaml
from pathlib import Path

# Define the paths to the Jekyll files relative to the project root
PROJECT_ROOT = Path(__file__).parent.parent.parent
JEKYLL_ROOT = PROJECT_ROOT / "blog"
CONFIG_PATH = JEKYLL_ROOT / "_config.yml"
ANALYTICS_PATH = JEKYLL_ROOT / "_includes" / "analytics.html"
HEAD_PATH = JEKYLL_ROOT / "_includes" / "head.html"


class TestMixpanelIntegration:
    """Tests for Mixpanel integration in Jekyll site."""

    def test_mixpanel_token_in_config(self):
        """Test that the Mixpanel token is properly configured in _config.yml."""
        assert CONFIG_PATH.exists(), f"Config file not found at {CONFIG_PATH}"
        
        # Read the config file
        with open(CONFIG_PATH, 'r') as f:
            config_content = f.read()
        
        # Check if mixpanel_token line exists in the raw content
        assert 'mixpanel_token:' in config_content, "mixpanel_token not found in _config.yml"
        
        # Verify the token is set to read from environment using Jekyll's !ENV tag
        assert "!ENV MIXPANEL_TOKEN" in config_content, \
            "mixpanel_token in _config.yml is not configured to use environment variable with !ENV tag"

    def test_analytics_file_includes_token(self):
        """Test that analytics.html properly initializes Mixpanel with the token."""
        assert ANALYTICS_PATH.exists(), f"Analytics file not found at {ANALYTICS_PATH}"
        
        # Read the analytics file
        with open(ANALYTICS_PATH, 'r') as f:
            analytics_content = f.read()
        
        # Check if the analytics file initializes Mixpanel with the token
        assert 'mixpanel.init("{{ site.mixpanel_token }}")' in analytics_content, \
            "Mixpanel initialization with token not found in analytics.html"
        
        # Check for page view tracking
        assert 'mixpanel.track("Page View"' in analytics_content, \
            "Page view tracking not found in analytics.html"

    def test_conditional_loading_in_production(self):
        """Test that Mixpanel is only loaded in production environment."""
        assert HEAD_PATH.exists(), f"Head file not found at {HEAD_PATH}"
        
        # Read the head file
        with open(HEAD_PATH, 'r') as f:
            head_content = f.read()
        
        # Check if Mixpanel is conditionally loaded in production
        production_check = re.search(r'{%\s*if\s+jekyll\.environment\s*==\s*"production"\s*%}', head_content)
        assert production_check is not None, "Production environment check not found in head.html"
        
        # Check if analytics is included inside the conditional
        analytics_include = re.search(r'{%\s*include\s+analytics\.html\s*%}', head_content)
        assert analytics_include is not None, "analytics.html inclusion not found in head.html"
        
        # Check if the conditional structure is complete
        endif_pattern = re.search(r'{%\s*endif\s*%}', head_content)
        assert endif_pattern is not None, "Conditional structure is incomplete in head.html"

    def test_mixpanel_script_integrity(self):
        """Test that the Mixpanel tracking script is properly included."""
        assert ANALYTICS_PATH.exists(), f"Analytics file not found at {ANALYTICS_PATH}"
        
        # Read the analytics file
        with open(ANALYTICS_PATH, 'r') as f:
            analytics_content = f.read()
        
        # Check for Mixpanel CDN script
        cdn_script = re.search(r'cdn\.mxpnl\.com/libs/mixpanel-2-latest\.min\.js', analytics_content)
        assert cdn_script is not None, "Mixpanel CDN script not found in analytics.html"


if __name__ == "__main__":
    pytest.main(["-v", __file__])