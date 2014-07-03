
class PeriodicTasks(object):
    '''
    This module contains 4 main functions:
        1. Accept user input through Nova API to create, update and delete checks
        2. Store checks and their parameters inside Ceilometer using (Ceilometer API?)
        3. Communicate with adapters for each running check
        4. Communicate with trusted_filer.py to provide it with a trusted compute pool 
            periodically or when user asks for get_trusted_pool
    This component also mediates communication with OpenAttestation (OA) for the trusted_filter
    unless it is not running, in which case the trusted_filter will call OA directly.             
    '''
    # map of nodes and their trusted status
    map_of_nodes = {}
    
    # list of running checks
    running_checks = [] 
    
    def __init__(self, params):
        ''' 
        TODO:
            a. Get information about checks from Ceilometer
            b. Initialize adapters for each check
            c. Communicate with trusted_filter and let it know of my existence
        '''
        pass
        
    def provideTrustedPool(self):
        # return the local trusted pool
        pass
    
    def addCheck(self):
        # add check to local list and update Ceilometer database
        pass
    
    def removeCheck(self):
        #  stop and delete adapter for this check and update Ceilometer database
        pass
    
    def acceptAdapterMessage(self):
        # update the local trusted pool
        pass
    