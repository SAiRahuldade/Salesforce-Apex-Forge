public class LeadProcessor implements Database.Batchable<sObject> {
    
    public Database.QueryLocator start(Database.BatchableContext bc) {
        // Collect all Leads in the org
        return Database.getQueryLocator('SELECT Id, LeadSource FROM Lead');
    }
    
    public void execute(Database.BatchableContext bc, List<Lead> scope) {
        // Process each batch of leads
        for (Lead l : scope) {
            l.LeadSource = 'Batch Processed';
        }
        update scope;
    }
    
    public void finish(Database.BatchableContext bc) {
        System.debug('LeadBatchProcessor: Batch processing completed successfully.');
    }
}