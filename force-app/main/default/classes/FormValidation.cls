public with sharing class FormValidation { 

    // Method to validate required fields
    public static void validateRequiredFields(List<Contact> contacts) {
        for(Contact contact : contacts) {
            if(String.isBlank(contact.FirstName)) {
                contact.addError('First Name is mandatory.');
            }
            if(String.isBlank(contact.LastName)) {
                contact.addError('Last Name is mandatory.');
            }
        }
    }

    // Method to validate data types
    public static void validateDataTypes(List<Contact> contacts) {
        for(Contact contact : contacts) {
            try {
                Integer.valueOf(contact.Age__c);
            } catch(Exception e) {
                contact.addError('Age must be a number.');
            }
        }
    }

    // Custom validation rule: age should be at least 18
    public static void validateAge(List<Contact> contacts) {
        for(Contact contact : contacts) {
            if(contact.Age__c != null && contact.Age__c < 18) {
                contact.addError('Age must be at least 18.');
            }
        }
    }
}