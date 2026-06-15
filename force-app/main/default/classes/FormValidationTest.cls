public with sharing class FormValidationTest {

    @IsTest
    public static void testValidateRequiredFields() {
        // Create a list of Contact records with missing required fields
        List<Contact> contacts = new List<Contact> {
            new Contact(FirstName='', LastName='Doe'),
            new Contact(FirstName='John', LastName='')
        };

        try {
            // Attempt to insert_CONTACTs, which should fail due to validation errors
            insert contacts;
            System.assert(false); // This line will not be executed if the test fails as expected
        } catch(DmlException e) {
            System.assert(e.getMessage().contains('First Name is mandatory.'));
            System.assert(e.getMessage().contains('Last Name is mandatory.'));
        }
    }

    @IsTest
    public static void testValidateDataTypes() {
        // Create a list of Contact records with incorrect data type for Age__c field
        List<Contact> contacts = new List<Contact> {
            new Contact(FirstName='John', LastName='Doe', Age__c='twenty')
        };

        try {
            // Attempt to insert_CONTACTs, which should fail due to validation errors
            insert contacts;
            System.assert(false); // This line will not be executed if the test fails as expected
        } catch(DmlException e) {
            System.assert(e.getMessage().contains('Age must be a number.'));
        }
    }

    @IsTest
    public static void testValidateAge() {
        // Create a list of Contact records with an age less than 18
        List<Contact> contacts = new List<Contact> {
            new Contact(FirstName='John', LastName='Doe', Age__c=17)
        };

        try {
            // Attempt to insert_CONTACTs, which should fail due to validation errors
            insert contacts;
            System.assert(false); // This line will not be executed if the test fails as expected
        } catch(DmlException e) {
            System.assert(e.getMessage().contains('Age must be at least 18.'));
        }
    }
}
