trigger ContactFormValidationTrigger on Contact (before insert, before update) {
    FormValidation.validateRequiredFields(Trigger.new);
    FormValidation.validateDataTypes(Trigger.new);
    FormValidation.validateAge(Trigger.new);
}