import hashlib

from ..models import TransactionRecord


def _clean_identifier(value: str) -> str:

    """
    清理标识符字符串，只保留字母和数字字符，并将所有字符转换为大写

    参数:
        value (str): 需要清理的原始字符串

    返回:
        str: 清理后的字符串，仅包含大写字母和数字
    """
    return "".join(character for character in value.upper() if character.isalnum())  # 生成器表达式过滤非字母数字字符并转换为大写


def _exact_key(record: TransactionRecord) -> str:
    """
    生成交易记录的唯一键值
    参数:
        record (TransactionRecord): 交易记录对象，包含交易的各种信息
    返回:
        str: 由多个交易字段组成的唯一键值，使用"|"连接
    """
    # 清理序列号标识符
    serial = _clean_identifier(record.serial_number)
    # 构建键值部分的元组
    parts = (
        # 如果序列号存在则使用"serial"，否则使用"fallback"
        "serial" if serial else "fallback",
        serial,
        # 将交易时间转换为ISO格式，并去除微秒部分
        record.transaction_time.replace(microsecond=0).isoformat(),
        # 付款账户
        record.payer_account,
        # 收款账户
        record.payee_account,
        # 货币代码转换为大写
        record.currency.upper(),
        # 金额格式化为两位小数的字符串
        f"{record.amount:.2f}",
    )
    # 使用"|"连接所有部分生成最终的键值字符串
    return "|".join(parts)


def _group_id(key: str) -> str:
    return f"DUP-{hashlib.sha256(key.encode('utf-8')).hexdigest()[:12].upper()}"


def group_duplicate_records(records: list[TransactionRecord]) -> list[TransactionRecord]:
    grouped = [
        record.model_copy(update={"duplicate_group": None, "conflict_status": None})
        for record in records
    ]
    serial_groups: dict[str, list[int]] = {}
    fallback_groups: dict[str, list[int]] = {}
    for index, record in enumerate(grouped):
        serial = _clean_identifier(record.serial_number)
        if serial:
            serial_groups.setdefault(serial, []).append(index)
        else:
            fallback_groups.setdefault(_exact_key(record), []).append(index)
    for indices in serial_groups.values():
        if len(indices) < 2:
            continue
        partitions: dict[str, list[int]] = {}
        for index in indices:
            partitions.setdefault(_exact_key(grouped[index]), []).append(index)
        if len(partitions) > 1:
            for index in indices:
                grouped[index].conflict_status = "same_serial_conflicting_fields"
        for key, partition_indices in partitions.items():
            if len(partition_indices) < 2:
                continue
            duplicate_group = _group_id(key)
            for index in partition_indices:
                grouped[index].duplicate_group = duplicate_group
    for key, indices in fallback_groups.items():
        if len(indices) > 1:
            duplicate_group = _group_id(key)
            for index in indices:
                grouped[index].duplicate_group = duplicate_group
    return grouped


def canonical_records(records: list[TransactionRecord]) -> list[TransactionRecord]:
    canonical: list[TransactionRecord] = []
    seen_groups: set[str] = set()
    for record in records:
        if record.duplicate_group:
            if record.duplicate_group in seen_groups:
                continue
            seen_groups.add(record.duplicate_group)
        canonical.append(record)
    return canonical
