"""
LINE Plugin for Dify
---------------------
This plugin enables integration between LINE messaging platform and Dify AI applications.
It handles webhook events from LINE, processes messages, and returns AI-generated responses.
"""

import os
import json
import logging
from typing import Dict, Any, List, Optional

from flask import request, Blueprint, Response, current_app
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage,
    SourceUser, FollowEvent, UnfollowEvent
)

from core.plugin.plugin import Plugin
from models.plugin import PluginConfiguration

# Set up logging
logger = logging.getLogger(__name__)

class LinePlugin(Plugin):
    def __init__(self):
        super().__init__(
            name="LINE Messaging",
            version="0.1.0",
            description="Integrates Dify with LINE messaging platform",
            icon="line-icon.svg",
            author="Dify Integration Team",
            author_url="https://dify.ai"
        )
        self.blueprint = Blueprint('line_plugin', __name__)
        self.line_bot_api = None
        self.handler = None
        self.dify_app_id = None
        
    def setup(self):
        """Initialize the plugin configuration and routes"""
        @self.blueprint.route('/webhook', methods=['POST'])
        def webhook():
            # Get X-Line-Signature header value
            signature = request.headers.get('X-Line-Signature')
            
            # Get request body as text
            body = request.get_data(as_text=True)
            logger.info(f"Request body: {body}")
            
            try:
                # Handle webhook body
                self.handler.handle(body, signature)
            except InvalidSignatureError:
                logger.error("Invalid signature. Check your channel secret.")
                return Response(status=400)
                
            return Response(status=200)
            
        @self.blueprint.route('/status', methods=['GET'])
        def status():
            """Return plugin status"""
            return {
                "status": "active",
                "version": self.version,
                "line_channel_connected": self.line_bot_api is not None
            }

    def load(self, config: Dict[str, Any]):
        """
        Load plugin with configuration
        
        Args:
            config: The plugin configuration containing LINE API credentials
        """
        if not config:
            logger.warning("LINE plugin configuration is empty")
            return
            
        channel_access_token = config.get('channel_access_token')
        channel_secret = config.get('channel_secret')
        self.dify_app_id = config.get('dify_app_id')
        
        if not channel_access_token or not channel_secret or not self.dify_app_id:
            logger.error("Missing required LINE configuration parameters")
            return
            
        try:
            self.line_bot_api = LineBotApi(channel_access_token)
            self.handler = WebhookHandler(channel_secret)
            
            # Register LINE event handlers
            self._register_event_handlers()
            
            logger.info("LINE plugin successfully loaded")
        except Exception as e:
            logger.error(f"Failed to initialize LINE client: {str(e)}")
    
    def _register_event_handlers(self):
        """Register handlers for LINE webhook events"""
        @self.handler.add(MessageEvent, message=TextMessage)
        def handle_text_message(event):
            """Handle incoming text messages"""
            user_id = event.source.user_id
            message = event.message.text
            
            # Get user profile information
            user_profile = self._get_user_profile(user_id)
            
            # Process message through Dify
            response = self._process_with_dify(message, user_id, user_profile)
            
            # Send response back to user
            if response:
                self.line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text=response)
                )
        
        @self.handler.add(FollowEvent)
        def handle_follow(event):
            """Handle when a user follows the LINE bot"""
            user_id = event.source.user_id
            user_profile = self._get_user_profile(user_id)
            
            # Send welcome message
            welcome_message = "Thanks for connecting! I'm your AI assistant powered by Dify. How can I help you today?"
            self.line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=welcome_message)
            )
            
            # Store user data if needed
            self._store_user_data(user_id, user_profile)
    
    def _get_user_profile(self, user_id: str) -> Dict[str, Any]:
        """
        Get LINE user profile information
        
        Args:
            user_id: LINE user ID
            
        Returns:
            User profile information
        """
        try:
            profile = self.line_bot_api.get_profile(user_id)
            return {
                "id": profile.user_id,
                "display_name": profile.display_name,
                "picture_url": profile.picture_url,
                "status_message": profile.status_message
            }
        except Exception as e:
            logger.error(f"Failed to get user profile: {str(e)}")
            return {"id": user_id}
    
    def _process_with_dify(self, message: str, user_id: str, user_profile: Dict[str, Any]) -> str:
        """
        Process message through Dify AI application
        
        Args:
            message: User message text
            user_id: LINE user ID
            user_profile: User profile information
            
        Returns:
            Response message from Dify
        """
        from extensions.ext_database import db
        from models.model import App
        
        try:
            # Get Dify application
            app = db.session.query(App).filter(App.id == self.dify_app_id).first()
            
            if not app:
                logger.error(f"Dify application not found: {self.dify_app_id}")
                return "Sorry, there was an error processing your request."
            
            # Create conversation context
            context = {
                "from_platform": "line",
                "user_id": user_id,
                "user_profile": user_profile
            }
            
            # Process through Dify application
            from core.application.app_runtime import AppRuntime
            app_runtime = AppRuntime()
            response = app_runtime.chat_message(
                app=app,
                query=message,
                context=context,
                user=None  # Anonymous user since it's from LINE
            )
            
            return response.get('answer', 'Sorry, I could not generate a response.')
            
        except Exception as e:
            logger.error(f"Failed to process message with Dify: {str(e)}")
            return "Sorry, there was an error processing your request."
    
    def _store_user_data(self, user_id: str, user_profile: Dict[str, Any]):
        """
        Store LINE user data in Dify database if needed
        
        Args:
            user_id: LINE user ID
            user_profile: User profile information
        """
        # Implement if user data storage is needed
        pass
    
    def get_configuration_schema(self) -> Dict[str, Any]:
        """
        Get the configuration schema for the plugin
        
        Returns:
            Configuration schema for LINE plugin
        """
        return {
            "type": "object",
            "required": ["channel_access_token", "channel_secret", "dify_app_id"],
            "properties": {
                "channel_access_token": {
                    "type": "string",
                    "title": "LINE Channel Access Token",
                    "description": "Channel Access Token from LINE Developers Console"
                },
                "channel_secret": {
                    "type": "string",
                    "title": "LINE Channel Secret",
                    "description": "Channel Secret from LINE Developers Console"
                },
                "dify_app_id": {
                    "type": "string",
                    "title": "Dify Application ID",
                    "description": "The ID of the Dify application to connect with LINE"
                },
                "welcome_message": {
                    "type": "string",
                    "title": "Welcome Message",
                    "description": "Message to send when a user first connects with your bot",
                    "default": "Thanks for connecting! I'm your AI assistant powered by Dify. How can I help you today?"
                }
            }
        }

    def unload(self):
        """Clean up resources when plugin is unloaded"""
        self.line_bot_api = None
        self.handler = None
        logger.info("LINE plugin unloaded")

# Create plugin instance
line_plugin = LinePlugin()

# Installation entry point
def install():
    return line_plugin

# Setup entry points for Dify plugin system
setup = line_plugin.setup
load = line_plugin.load
unload = line_plugin.unload
bp = line_plugin.blueprint
