from oslo.config import cfg

from inspect import getfile
from os import path
import threading

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
    cfg.IntOpt('spacing',
                default=10,
                help='Periodic check spacing time'),
    cfg.BoolOpt('saved_trusted_pool',
                default=False,
                help='Whether save trusted pool')
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
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(PeriodicChecks, cls).__new__(
                                cls, *args, **kwargs)
        return cls._instance

    def __init__(self):
        admin = context.get_admin_context()
        self.cache_spacing = {}
        self.spacing = CONF.periodic_checks.spacing
        ''' all compute nodes '''
        self.compute_nodes = {}
        '''all attached adapters '''
        self.class_map = {}
        self.adapter_list = self._get_all_adapters()
        self.initialize_trusted_pool(admin)
        self._initialize_DB(admin)

    def _initialize_DB(self, context):
        for adapter in self.adapter_list:
            check = db.periodic_check_get(context, self._get_name(adapter))
            if not check:
                check = {'name':self._get_name(adapter), 'spacing' : 60, 'desc': adapter.__name__, 'timeout':10}
                self.add_check(context, check);
            self.cache_spacing[check['name']] = check['spacing']

    def initialize_trusted_pool(self, context):
        computes = db.compute_node_get_all(context)
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
        return classes

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
        self.adapter_list = self._get_all_adapters()

    def remove_check(self, context, values):
        ''' stop and delete adapter for this check and update mysql database
        '''
        name = values['name']
        '''Don't allow Open Attestation check to be removed
        '''
        if name.lower() == "ComputeAttestationAdapter".lower():
            raise exception.CannotDeleteOpenAttestationPeriodicCheck()
        db.periodic_check_delete(context, name)
        self.adapter_list = self._get_all_adapters()

    def update_check(self, context, values):
        name = values['name']
        db.periodic_check_update(context, name, values)
        self.cache_spacing[name] = values['spacing']

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

    def set_save_trusted_pool(self):
        CONF.periodic_checks.saved_trusted_pool = True
        
    def set_unsave_trusted_pool(self):
        CONF.periodic_checks.saved_trusted_pool = False

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
            for host in input_nodes:
                for adapter in self.adapter_list:
                    adapter_instance = adapter()
                    check = db.periodic_check_get(context,
                                                  adapter_instance.get_name())
                    self.run_check_and_store_result(context, host, check,
                                                    adapter_instance)

    def run_checks(self, context):
        ''' Store results of each check periodically
        '''
        if(PeriodicChecks.periodic_tasks_running):
            for host in self.compute_nodes:
                for adapter in self.adapter_list:
                    adapter_instance = adapter()
                    check = db.periodic_check_get(context,
                        self._get_name(adapter))
                    self.cache_spacing[check['name']] += self.spacing
                    if self.cache_spacing[check['name']] >= check['spacing']:
                        self.run_check_and_store_result(context, host,
                            check, adapter_instance)
                        self.cache_spacing[check['name']] = 0

    def run_check_and_store_result(self, context, host, check,
                                    adapter_instance):
        LOG.debug("Periodic check store result into DB[%s]", host)
        class CheckThread(threading.Thread):
            def __init__(self):
                threading.Thread.__init__(self)
                self.status = 'timeout'
                self.result = False
            def run(self):
                self.result, self.status = adapter_instance.is_trusted(host, 'trusted')

            def _stop(self):
                if self.isAlive():
                    threading.Thread._Thread__stop(self)

        check_thread = CheckThread()
        check_thread.start()
        if check['timeout']:
            check_thread.join(check['timeout'])
        else:
            check_thread.join()
        if check_thread.isAlive():
            check_thread._stop()

        current_host = self.compute_nodes[host]
        current_host['trust_lvl'] = check_thread.result

        '''store data'''
        check_result = {'check_id': check.id,
                        'check_name': check.name,
                        'time': timeutils.strtime(),
                        'node': host,
                        'result': check_thread.result,
                        'status': check_thread.status}

        '''maintain trusted pool'''
        self.compute_nodes[host] = {
                        'trust_lvl': check_thread.result,
                        'vtime': timeutils.utcnow_ts()}

        db.periodic_check_results_store(context, check_result)

    def _get_name(self, className):
        return path.splitext(path.basename(getfile(className)))[0]

