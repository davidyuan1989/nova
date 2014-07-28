from oslo.config import cfg

from nova import context
from nova import db
from nova import exception
from nova.openstack.common import timeutils
from nova.openstack.common import log as logging
from nova.scheduler import adapters

LOG = logging.getLogger(__name__)

check_opts = [
    cfg.BoolOpt('periodic_tasks_running',
                default=True,
                help='Periodic check status'),
]

CONF = cfg.CONF
check_group = cfg.OptGroup(name='periodic_checks',
                           title='Periodic check parameters')
CONF.register_group(check_group)
CONF.register_opts(check_opts, group=check_group)


class PeriodicChecks(object):
    '''This module contains 4 main functions:
        1. Accept user input through Nova API to create, update and
                delete checks
        2. Store checks and their parameters inside SQLAlchemy
        3. Communicate with adapters for each running check
        4. Communicate with trusted_filer.py to provide it with a
                trusted compute pool when needed.
    This component also mediates communication with OpenAttestation
    (OA) for the trusted_filter unless it is not running, in which case
    the trusted_filter will call OA directly.
    '''

    ''' periodic tasks not running by default '''
    periodic_tasks_running = True

    def __init__(self):
        self.compute_nodes = {}
        ''' get all adapters '''
        self.adapter_handler = adapters.AdapterHandler()
        ''' all compute nodes '''
        self.compute_nodes = {}
        '''all attached adapters '''
        self.class_map = {}
        self.initialize_trusted_pool()

    def initialize_trusted_pool(self):
        admin = context.get_admin_context()
        computes = db.compute_node_get_all(admin)
        for compute in computes:
            service = compute['service']
            host = service['host']
            self._init_cache_entry(host)

    def _init_cache_entry(self, host):
        self.compute_nodes[host] = {
            'trust_lvl': 'unknown',
            'vtime': timeutils.normalize_time(
                timeutils.parse_isotime("1970-01-01T00:00:00Z"))}

    def _get_all_adapters(self):
        adapter_handler = adapters.AdapterHandler()
        classes = adapter_handler.get_matching_classes(
            ['nova.scheduler.adapters.all_adapters'])
        class_map = {}
        for cls in classes:
            class_map[cls.__name__] = cls
        return class_map

    ''' Add checks through horizon
    @param id: identifier for the check
    @param spacing: time between successive checks in seconds
    @param type-of_check: (optional) any additional info about of the check
    '''
    def add_check(self, context, values):
        ''' check_id = kwargs['id']
        set the periodic tasks running flag to True
        TODO write new check into CONF and then call adapter
        '''
        CONF.periodic_checks.periodic_tasks_running = True
        db.periodic_check_create(context, values)

    def remove_check(self, context, values):
        ''' stop and delete adapter for this check and update mysql database
        '''
        name = values['name']
        '''Don't allow Open Attestation check to be removed
        '''
        if name.lower() == "ComputeAttestationAdapter".lower():
            raise exception.CannotDeleteOpenAttestationPeriodicCheck()
        db.periodic_check_delete(context, name)

    def update_check(self, context, values):
        name = values['name']
        db.periodic_check_update(context, name, values)

    def get_check_by_name(self, context, values):
        name = values['name']
        return db.periodic_check_get(context, name)

    def get_all_checks(self, context):
        return db.periodic_check_get_all(context)

    def is_periodic_checks_running(self):
        ''' Used to check of periodic tasks are running by
        scheduler.filters.trusted_filter
        '''
        if CONF.periodic_checks.periodic_tasks_running:
            return True
        return False

    def get_running_checks(self):
        if CONF.periodic_checks.periodic_tasks_running:
            return db.periodic_check_get_all
        return None

    def get_trusted_pool(self):
        if CONF.periodic_checks.periodic_tasks_running:
            return self.compute_nodes
        return None

    def turn_off_periodic_check(self):
        CONF.periodic_checks.periodic_tasks_running = False

    def turn_on_periodic_check(self):
        CONF.periodic_checks.periodic_tasks_running = True

    '''return 100 check resutls by default'''
    def periodic_checks_results_get(self, context, num_of_results=100):
        results = db.periodic_check_results_get(context, num_of_results)
        return results

    def periodic_checks_results_delete_by_id(self, context, id):
        result = db.periodic_check_results_delete_by_id(context, id)
        return result

    '''Runs a check manually on an input list of nodes so that previously
    removed node can be returned to trusted pool
    '''
    def run_checks_specific_nodes(self, context, input_nodes):
        if(PeriodicChecks.periodic_tasks_running):
            adapters = self._get_all_adapters()
            for host in input_nodes:
                for index, adapter in enumerate(adapters):
                    adapter_instance = adapters[adapter]()
                    self.run_check_and_store_result(context, host, adapter, adapter_instance)

    def run_checks(self, context):
        ''' Store results of each check periodically
        '''

        if(PeriodicChecks.periodic_tasks_running):
            adapters = self._get_all_adapters()
            for host in self.compute_nodes:
                LOG.debug("host:[%s]",host)
                for index, adapter in enumerate(adapters):
                    LOG.debug("adapter:[%s]",adapter)
                    adapter_instance = adapters[adapter]()
                    self.run_check_and_store_result(context, host, adapter, adapter_instance)

    def run_check_and_store_result(self, context, host, adapter_name, adapter_instance):
        LOG.debug("Periodic check store result into DB[%s]", host)
        result, turn_on = adapter_instance.is_trusted(host, 'trusted')
        if turn_on:
            current_host = self.compute_nodes[host]
            current_host['trust_lvl'] = result
            '''store data'''
            check = {'name': adapter_name,
                    'time': timeutils.utcnow_ts(),
                    'node': host,
                    'result': result,
                    'status': 'on'}
            
            '''maintain trusted pool
            '''
            self.compute_nodes[host] = {
                            'trust_lvl': result,
                            'vtime': timeutils.normalize_time(
                                timeutils.parse_isotime("1970-01-01T00:00:00Z"))}
        else:
            '''not store data'''
            check = {'name': adapter_name,
                    'time' : timeutils.utcnow_ts(),
                    'node': host,
                    'result': result,
                    'status': 'off'}
        db.periodic_check_results_store(context, check)
