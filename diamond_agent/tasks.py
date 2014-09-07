import os
import sys
import glob
from shutil import copytree
from tempfile import mkdtemp
from subprocess import call
from cloudify.decorators import operation
from cloudify.utils import get_manager_ip
from configobj import ConfigObj

# TODO: place log in homedir
# TODO: paths cannot be unix only
# TODO: check if kill cannot be signal 9
# TODO: add possibility to configure default collectors from BP

CONFIG_NAME = 'diamond.conf'

@operation
def install(ctx, **kwargs):

    try:
        prefix = ctx.properties['config']['path']
    except KeyError:
        prefix = mkdtemp(prefix='cloudify-')

    ctx.runtime_properties['diamond_config_path'] = \
        os.path.join(prefix, 'etc')
    if not os.path.isdir(ctx.runtime_properties['diamond_config_path']):
        os.makedirs(ctx.runtime_properties['diamond_config_path'])

    ctx.runtime_properties['diamond_col_conf_path'] = \
        os.path.join(prefix, 'collectors')
    # if not os.path.isdir(ctx.runtime_properties['diamond_col_conf_path']):
    #     os.makedirs(ctx.runtime_properties['diamond_col_conf_path'])
    copytree(os.path.join(sys.prefix, 'etc', 'diamond', 'collectors'),
             ctx.runtime_properties['diamond_col_conf_path'])

    ctx.runtime_properties['diamond_col_path'] = \
        os.path.join(sys.prefix, 'share', 'diamond', 'collectors')

    ctx.runtime_properties['diamond_hdl_conf_path'] = \
        os.path.join(prefix, 'handlers')
    if not os.path.isdir(ctx.runtime_properties['diamond_hdl_conf_path']):
        os.makedirs(ctx.runtime_properties['diamond_hdl_conf_path'])

    ctx.runtime_properties['diamond_handlers'] = \
        'cloudify_handler.cloudify.CloudifyHandler'

    create_config(ctx)
    disable_all_collectors(ctx.runtime_properties['diamond_col_conf_path'])
    enable_collectors(ctx.runtime_properties['diamond_col_conf_path'],
                      ['CPUCollector', 'MemoryCollector',
                       'LoadAverageCollector', 'DiskUsageCollector'])

    config_cloudify_handler(
        os.path.join(ctx.runtime_properties['diamond_hdl_conf_path'],
                     'CloudifyHandler.conf'))
    # start(ctx)


@operation
def uninstall(ctx, **kwargs):
    pass


@operation
def start(ctx, **kwargs):
    cmd = 'diamond --configfile {}'\
        .format(os.path.join(ctx.runtime_properties['diamond_config_path'],
                             CONFIG_NAME))
    try:
        call(cmd.split())
    except OSError:
        ctx.logger.info('Failed starting Diamond')


@operation
def stop(ctx, **kwargs):
    with open ('/tmp/diamond.pid') as f:
        pid = int(f.read())

    try:
        os.kill(pid, 9)
    except OSError:
        ctx.logger.info('Failed stopping Diamond')


def enable_collector(path, collector):
    conf_path = os.path.join(path, collector + '.conf')
    config = ConfigObj(infile=conf_path, file_error=True)
    config['enabled'] = True
    config.write()


def disable_collector(path, collector):
    conf_path = os.path.join(path, collector + '.conf')
    config = ConfigObj(infile=conf_path, file_error=True)
    config['enabled'] = False
    config.write()


def enable_collectors(path, collectors):
    for collector in collectors:
        enable_collector(path, collector)


def disable_all_collectors(path):
    files = glob.glob(os.path.join(path, '*.conf'))
    for f in files:
        collector = os.path.splitext(os.path.basename(f))[0]
        disable_collector(path, collector)


def config_cloudify_handler(config_path):
    handler_config = {
        'rmq_server': get_manager_ip(),
        'rmq_port': 5672,
        'rmq_exchange': 'monitoring',
        'rmq_user': '',
        'rmq_password': '',
        'rmq_vhost': '/',
        'rmq_exchange_type': 'topic',
        'rmq_durable': False
    }
    config = ConfigObj(handler_config, write_empty_values=True)
    config.filename = config_path
    config.write()


def copy_collectors(ctx):
    pass


def create_config(ctx):
    """
    Create config file and write it into config_path
    """
    server_config = {
        'server': {
            'handlers': ctx.runtime_properties['diamond_handlers'],
            'user': '',
            'group': '',
            'pid_file': '/tmp/diamond.pid',
            'collectors_path': ctx.runtime_properties['diamond_col_path'],
            'collectors_config_path':
                    ctx.runtime_properties['diamond_col_conf_path'],
            'handlers_config_path':
                    ctx.runtime_properties['diamond_hdl_conf_path'],
            'handlers_path': '/usr/share/diamond/handlers/',
            'collectors_reload_interval': 3600,
        },
        'handlers': {
            'keys': 'rotated_file',
            'default': {},
        },
        'collectors': {
            'default': {
                'hostname': '.'.join([ctx.node_name, ctx.node_id]),
                'path_prefix': ctx.deployment_id,
                'interval': ctx.properties['config']['interval'],
            },
        },
        'loggers': {
            'keys': 'root',
        },
        'formatters': {
            'keys': 'default',
        },
        'logger_root': {
            'level': 'INFO',
            'handlers': 'rotated_file',
            'propagate': 1,
        },
        'handler_rotated_file': {
            'class': 'handlers.TimedRotatingFileHandler',
            'level': 'DEBUG',
            'formatter': 'default',
            # 'args': '({}, {}, 1, 7)'.format('/tmp/diamond.log', 'midnight'),
            'args': "('/tmp/diamond.log', 'midnight', 1, 7)",
        },
        'formatter_default': {
            'format': '[%(asctime)s] [%(threadName)s] %(message)s',
            'datefmt': '',
        },
    }
    config = ConfigObj(server_config,
                       indent_type='',
                       list_values=False,
                       write_empty_values=True)
    config.filename = os.path.join(
        ctx.runtime_properties['diamond_config_path'], CONFIG_NAME)
    config.write()
