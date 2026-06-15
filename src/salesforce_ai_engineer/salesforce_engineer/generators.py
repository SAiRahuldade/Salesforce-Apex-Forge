"""
Code generators for Salesforce artifacts.

Generates production-ready Apex classes, Lightning Web Components, Flows,
and metadata following Salesforce best practices.
"""

from __future__ import annotations

import logging
from typing import Any, Optional


class ApexGenerator:
    """Generates production-ready Apex code."""

    def __init__(self, logger: Optional[logging.Logger] = None) -> None:
        self.logger = logger or logging.getLogger(__name__)

    async def generate_apex(
        self,
        task_input: dict[str, Any],
        context: dict[str, Any],
    ) -> str:
        """Generate Apex class from task input.
        
        Args:
            task_input: Task input containing class specification
            context: Execution context
            
        Returns:
            Generated Apex code
        """
        class_name = task_input.get("class_name", "GeneratedClass")
        class_type = task_input.get("type", "standard")  # standard, batch, queueable, scheduled
        methods = task_input.get("methods", [])
        properties = task_input.get("properties", [])
        
        code = f"""/**
 * {class_name}
 * 
 * Auto-generated Salesforce Apex class
 * Generated: {context.get('timestamp', 'unknown')}
 */
public {'with sharing' if task_input.get('with_sharing', True) else ''} class {class_name}"""
        
        # Add implements clause based on type
        implements = []
        if class_type == "batch":
            implements.append("Database.Batchable<SObject>")
        elif class_type == "queueable":
            implements.append("Queueable")
        elif class_type == "scheduled":
            implements.append("Schedulable")
        
        if implements:
            code += f" implements {', '.join(implements)}"
        
        code += " {\n"
        
        # Add properties
        if properties:
            code += "\n    // Properties\n"
            for prop in properties:
                visibility = prop.get("visibility", "private")
                prop_type = prop.get("type", "Object")
                prop_name = prop.get("name")
                default_value = prop.get("default")
                
                code += f"    {visibility} {prop_type} {prop_name}"
                if default_value:
                    code += f" = {default_value}"
                code += ";\n"
        
        # Add constructor
        code += f"\n    /**\n     * Constructor\n     */\n"
        code += f"    public {class_name}() {{\n"
        code += "        // Initialize\n"
        code += "    }\n"
        
        # Add methods
        if methods:
            code += "\n    // Methods\n"
            for method in methods:
                method_name = method.get("name")
                return_type = method.get("return_type", "void")
                visibility = method.get("visibility", "public")
                parameters = method.get("parameters", [])
                body = method.get("body", "        // TODO: Implement")
                
                param_str = ", ".join([f"{p.get('type')} {p.get('name')}" for p in parameters])
                
                code += f"\n    /**\n     * {method_name}\n     */\n"
                code += f"    {visibility} {return_type} {method_name}({param_str}) {{\n"
                code += f"{body}\n"
                code += "    }\n"
        
        # Add Batchable implementation if needed
        if class_type == "batch":
            code += """
    public Database.QueryLocator start(Database.BatchableContext bc) {
        return Database.getQueryLocator('SELECT Id FROM SObject LIMIT 1000');
    }
    
    public void execute(Database.BatchableContext bc, List<SObject> scope) {
        // Implement batch logic
    }
    
    public void finish(Database.BatchableContext bc) {
        // Handle batch completion
    }
"""
        
        # Add Queueable implementation if needed
        if class_type == "queueable":
            code += """
    public void execute(QueueableContext context) {
        // Implement queueable logic
    }
"""
        
        # Add Schedulable implementation if needed
        if class_type == "scheduled":
            code += """
    public void execute(SchedulableContext context) {
        // Implement scheduled logic
    }
"""
        
        code += "}\n"
        
        return code


class LWCGenerator:
    """Generates production-ready Lightning Web Components."""

    def __init__(self, logger: Optional[logging.Logger] = None) -> None:
        self.logger = logger or logging.getLogger(__name__)

    async def generate_lwc(
        self,
        task_input: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, str]:
        """Generate LWC files from task input.
        
        Args:
            task_input: Task input containing component specification
            context: Execution context
            
        Returns:
            Dictionary of filename -> code
        """
        component_name = task_input.get("component_name", "generatedComponent")
        properties = task_input.get("properties", [])
        methods = task_input.get("methods", [])
        template = task_input.get("template", "<template></template>")
        
        # Generate JavaScript
        js_code = f"""import {{ LightningElement, api }} from 'lwc';

/**
 * {component_name}
 * Auto-generated Lightning Web Component
 */
export default class {self._to_pascal_case(component_name)} extends LightningElement {{
    // Properties
"""
        
        for prop in properties:
            prop_type = prop.get("type", "String")
            prop_name = prop.get("name")
            default_value = prop.get("default", "")
            
            if prop.get("api"):
                js_code += f"    @api {prop_name}";
            else:
                js_code += f"    {prop_name}";
            
            if default_value:
                js_code += f" = {default_value}"
            js_code += ";\n"
        
        js_code += "\n    // Methods\n"
        for method in methods:
            method_name = method.get("name")
            parameters = method.get("parameters", [])
            body = method.get("body", "        // TODO: Implement")
            
            param_str = ", ".join(parameters)
            js_code += f"\n    {method_name}({param_str}) {{\n"
            js_code += f"{body}\n"
            js_code += "    }\n"
        
        js_code += "}\n"
        
        # Generate HTML
        html_code = f"""<template>
    <!-- {component_name} -->
    {template}
</template>\n"""
        
        # Generate CSS
        css_code = """:host {{
    --lwc-padding: 1rem;
}}

.container {{
    padding: var(--lwc-padding);
}}
"""
        
        # Generate meta.xml
        meta_code = f"""<?xml version="1.0" encoding="UTF-8"?>
<LightningComponentBundle xmlns="http://soap.sforce.com/2006/04/metadata">
    <apiVersion>58.0</apiVersion>
    <isExposed>true</isExposed>
    <targets>
        <target>lightning__RecordPage</target>
        <target>lightning__AppPage</target>
    </targets>
</LightningComponentBundle>
"""
        
        return {
            f"{component_name}.js": js_code,
            f"{component_name}.html": html_code,
            f"{component_name}.css": css_code,
            f"{component_name}.js-meta.xml": meta_code,
        }

    @staticmethod
    def _to_pascal_case(snake_str: str) -> str:
        """Convert snake_case to PascalCase."""
        return "".join(word.capitalize() for word in snake_str.split("_"))


class FlowGenerator:
    """Generates Salesforce Flow definitions."""

    def __init__(self, logger: Optional[logging.Logger] = None) -> None:
        self.logger = logger or logging.getLogger(__name__)

    async def generate_flow(
        self,
        task_input: dict[str, Any],
        context: dict[str, Any],
    ) -> str:
        """Generate Flow XML from task input.
        
        Args:
            task_input: Task input containing flow specification
            context: Execution context
            
        Returns:
            Generated Flow XML
        """
        flow_name = task_input.get("flow_name", "GeneratedFlow")
        flow_type = task_input.get("type", "Flow")  # Flow, AutoLaunchedFlow, etc.
        description = task_input.get("description", "Auto-generated flow")
        start_element = task_input.get("start_element", "start")
        
        xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Flow xmlns="http://soap.sforce.com/2006/04/metadata">
    <apiVersion>58.0</apiVersion>
    <definition>
        <name>{flow_name}</name>
        <type>{flow_type}</type>
        <description>{description}</description>
        <startElementReference>{start_element}</startElementReference>
        
        <!-- Variables -->
        <variables>
            <name>recordId</name>
            <dataType>String</dataType>
            <isCollection>false</isCollection>
            <isInput>true</isInput>
            <isOutput>false</isOutput>
        </variables>
        
        <!-- Decision Element -->
        <decisions>
            <name>Check_Record_Type</name>
            <label>Check Record Type</label>
            <locationX>100</locationX>
            <locationY>100</locationY>
            <defaultConnectorLabel>Default</defaultConnectorLabel>
            <rules>
                <name>Rule_1</name>
                <conditionLogic>and</conditionLogic>
                <conditions>
                    <leftValueReference>recordId</leftValueReference>
                    <operator>NotEqualTo</operator>
                    <rightValue></rightValue>
                </conditions>
                <connector>
                    <targetReference>Display_Record</targetReference>
                </connector>
                <label>Has Record ID</label>
            </rules>
        </decisions>
        
        <!-- Screen Element -->
        <screens>
            <name>Display_Record</name>
            <label>Display Record</label>
            <locationX>200</locationY>
            <locationY>200</locationY>
            <allowBack>true</allowBack>
            <allowFinish>true</allowFinish>
            <showFooter>true</showFooter>
            <showHeader>true</showHeader>
            <fields>
                <name>recordInfo</name>
                <fieldType>DisplayText</fieldType>
                <value>
                    <stringValue>Record processed successfully</stringValue>
                </value>
            </fields>
        </screens>
        
    </definition>
</Flow>
"""
        
        return xml


class MetadataGenerator:
    """Generates Salesforce metadata definitions."""

    def __init__(self, logger: Optional[logging.Logger] = None) -> None:
        self.logger = logger or logging.getLogger(__name__)

    async def generate_metadata(
        self,
        task_input: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Generate metadata definition from task input.
        
        Args:
            task_input: Task input containing metadata specification
            context: Execution context
            
        Returns:
            Metadata definition
        """
        metadata_type = task_input.get("type", "CustomObject")
        
        if metadata_type == "CustomObject":
            return self._generate_custom_object(task_input)
        elif metadata_type == "PermissionSet":
            return self._generate_permission_set(task_input)
        elif metadata_type == "Profile":
            return self._generate_profile(task_input)
        elif metadata_type == "ValidationRule":
            return self._generate_validation_rule(task_input)
        else:
            return self._generate_generic_metadata(task_input)

    @staticmethod
    def _generate_custom_object(task_input: dict[str, Any]) -> dict[str, Any]:
        """Generate custom object metadata."""
        return {
            "name": task_input.get("object_name", "Custom_Object__c"),
            "type": "CustomObject",
            "label": task_input.get("label", "Custom Object"),
            "plural": task_input.get("plural", "Custom Objects"),
            "description": task_input.get("description", ""),
            "fields": task_input.get("fields", []),
            "recordTypes": task_input.get("record_types", []),
            "validation_rules": task_input.get("validation_rules", []),
            "sharing_rules": task_input.get("sharing_rules", []),
        }

    @staticmethod
    def _generate_permission_set(task_input: dict[str, Any]) -> dict[str, Any]:
        """Generate permission set metadata."""
        return {
            "name": task_input.get("name", "Generated_PermSet"),
            "type": "PermissionSet",
            "label": task_input.get("label", "Generated Permission Set"),
            "description": task_input.get("description", ""),
            "object_permissions": task_input.get("object_permissions", []),
            "field_permissions": task_input.get("field_permissions", []),
            "user_permissions": task_input.get("user_permissions", []),
        }

    @staticmethod
    def _generate_profile(task_input: dict[str, Any]) -> dict[str, Any]:
        """Generate profile metadata."""
        return {
            "name": task_input.get("name", "Generated_Profile"),
            "type": "Profile",
            "description": task_input.get("description", ""),
            "object_permissions": task_input.get("object_permissions", []),
            "field_permissions": task_input.get("field_permissions", []),
        }

    @staticmethod
    def _generate_validation_rule(task_input: dict[str, Any]) -> dict[str, Any]:
        """Generate validation rule metadata."""
        return {
            "name": task_input.get("name", "Validation_Rule"),
            "type": "ValidationRule",
            "object": task_input.get("object", "Account"),
            "formula": task_input.get("formula", "false"),
            "error_message": task_input.get("error_message", "Validation failed"),
            "error_location": task_input.get("error_location", ""),
        }

    @staticmethod
    def _generate_generic_metadata(task_input: dict[str, Any]) -> dict[str, Any]:
        """Generate generic metadata."""
        return {
            "type": task_input.get("type", "Metadata"),
            "name": task_input.get("name", "Generated_Metadata"),
            "definition": task_input.get("definition", {}),
        }
