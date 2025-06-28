from media_organizer.app.logger import Logger
import tempfile

def test_logger_info_and_file(tmp_path):
    log_file = tmp_path / 'log.txt'
    logger = Logger(str(log_file))
    logger.info('hello')
    logger.error('fail')
    with open(log_file) as f:
        content = f.read()
    assert 'hello' in content
    assert 'fail' in content
