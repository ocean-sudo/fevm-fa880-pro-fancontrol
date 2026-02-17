/*
 * FEVM FA880 PRO Fan Control via ACPI-WMI
 * 
 * WMI GUID: 99D89064-8D50-42BB-BEA9-155B2E5D0FCD
 * Method ID: 3 (SetFanControl)
 * 
 * Input:  uint8 FanNumber (1=CPU, 2=Memory)
 *         uint8 FanDuty (0-100)
 * Output: uint8 ResultStatus (0=success)
 */

#include <linux/module.h>
#include <linux/kernel.h>
#include <linux/init.h>
#include <linux/sysfs.h>
#include <linux/device.h>
#include <linux/platform_device.h>
#include <linux/wmi.h>
#include <linux/acpi.h>
#include <linux/slab.h>

#define DRV_NAME "fevm-ip3-wmi"
#define WMI_GUID "99D89064-8D50-42BB-BEA9-155B2E5D0FCD"
#define METHOD_ID_SET_FAN_CONTROL 3

/* Platform device for sysfs interface */
static struct platform_device *fevm_pdev;

static struct wmi_device *fan_wmi_dev;

/*
 * Call SetFanControl WMI method
 * @fan_num: 1 = CPU fan, 2 = Memory fan
 * @duty: 0-100 (percentage)
 * Returns: 0 on success, negative on error
 */
static int fevm_set_fan_control(u8 fan_num, u8 duty)
{
	struct acpi_buffer input;
	struct acpi_buffer output;
	acpi_status status;
	union acpi_object *result;
	u8 input_data[2];
	int ret = 0;

	if (!fan_wmi_dev) {
		pr_err("%s: WMI device not available\n", DRV_NAME);
		return -ENODEV;
	}

	/* Clamp duty to 0-100 */
	if (duty > 100)
		duty = 100;

	/* Prepare input: two uint8 values */
	input_data[0] = fan_num;  /* FanNumber (ID=0) */
	input_data[1] = duty;     /* FanDuty (ID=1) */

	input.length = sizeof(input_data);
	input.pointer = input_data;

	/* Output buffer */
	output.length = ACPI_ALLOCATE_BUFFER;
	output.pointer = NULL;

	pr_info("%s: Calling SetFanControl(FanNumber=%u, FanDuty=%u)\n",
		DRV_NAME, fan_num, duty);

	/* Call WMI method */
	status = wmidev_evaluate_method(fan_wmi_dev, 0, METHOD_ID_SET_FAN_CONTROL,
					&input, &output);

	if (ACPI_FAILURE(status)) {
		pr_err("%s: WMI method call failed: %s\n", DRV_NAME,
			acpi_format_exception(status));
		return -EIO;
	}

	/* Parse output */
	result = output.pointer;
	if (!result) {
		pr_err("%s: No output from WMI method\n", DRV_NAME);
		return -EIO;
	}

	if (result->type == ACPI_TYPE_INTEGER) {
		u8 result_status = (u8)result->integer.value;
		pr_info("%s: SetFanControl result: ResultStatus=%u\n",
			DRV_NAME, result_status);
		if (result_status != 0) {
			pr_err("%s: SetFanControl failed with status %u\n",
				DRV_NAME, result_status);
			ret = -EIO;
		}
	} else if (result->type == ACPI_TYPE_BUFFER && result->buffer.length >= 1) {
		/* Sometimes result is returned as a buffer */
		u8 result_status = result->buffer.pointer[0];
		pr_info("%s: SetFanControl result (buffer): ResultStatus=%u\n",
			DRV_NAME, result_status);
		if (result_status != 0) {
			pr_err("%s: SetFanControl failed with status %u\n",
				DRV_NAME, result_status);
			ret = -EIO;
		}
	} else {
		pr_warn("%s: Unexpected result type: %d\n", DRV_NAME, result->type);
	}

	kfree(output.pointer);
	return ret;
}

/*
 * Sysfs attribute: fan1_duty (CPU fan)
 */
static ssize_t fan1_duty_show(struct device *dev,
			      struct device_attribute *attr, char *buf)
{
	/* Reading current duty is not supported by this WMI interface */
	return sprintf(buf, "N/A (write-only)\n");
}

static ssize_t fan1_duty_store(struct device *dev,
			       struct device_attribute *attr,
			       const char *buf, size_t count)
{
	unsigned long duty;
	int ret;

	if (kstrtoul(buf, 10, &duty))
		return -EINVAL;

	if (duty > 100)
		duty = 100;

	/* FanNumber=1 for CPU fan */
	ret = fevm_set_fan_control(1, (u8)duty);
	if (ret)
		return ret;

	return count;
}
static DEVICE_ATTR_RW(fan1_duty);

/*
 * Sysfs attribute: fan2_duty (Memory fan)
 */
static ssize_t fan2_duty_show(struct device *dev,
			      struct device_attribute *attr, char *buf)
{
	return sprintf(buf, "N/A (write-only)\n");
}

static ssize_t fan2_duty_store(struct device *dev,
			       struct device_attribute *attr,
			       const char *buf, size_t count)
{
	unsigned long duty;
	int ret;

	if (kstrtoul(buf, 10, &duty))
		return -EINVAL;

	if (duty > 100)
		duty = 100;

	/* FanNumber=2 for Memory fan */
	ret = fevm_set_fan_control(2, (u8)duty);
	if (ret)
		return ret;

	return count;
}
static DEVICE_ATTR_RW(fan2_duty);

/*
 * WMI Driver
 */
static int fevm_wmi_probe(struct wmi_device *wdev, const void *context)
{
	pr_info("%s: WMI device probed: %s\n", DRV_NAME, WMI_GUID);
	fan_wmi_dev = wdev;
	return 0;
}

static void fevm_wmi_remove(struct wmi_device *wdev)
{
	pr_info("%s: WMI device removed\n", DRV_NAME);
	fan_wmi_dev = NULL;
}

static const struct wmi_device_id fevm_wmi_id_table[] = {
	{ .guid_string = WMI_GUID },
	{ }
};
MODULE_DEVICE_TABLE(wmi, fevm_wmi_id_table);

static struct wmi_driver fevm_wmi_driver = {
	.driver = {
		.name = DRV_NAME,
	},
	.id_table = fevm_wmi_id_table,
	.probe = fevm_wmi_probe,
	.remove = fevm_wmi_remove,
};

/*
 * Platform device for sysfs
 */
static struct attribute *fevm_attrs[] = {
	&dev_attr_fan1_duty.attr,
	&dev_attr_fan2_duty.attr,
	NULL,
};

static struct attribute_group fevm_attr_group = {
	.attrs = fevm_attrs,
};

static const struct attribute_group *fevm_attr_groups[] = {
	&fevm_attr_group,
	NULL,
};

static struct platform_device *fevm_pdev;

static int __init fevm_init(void)
{
	int ret;

	pr_info("%s: Initializing FEVM FA880 PRO Fan Control\n", DRV_NAME);

	/* Register WMI driver */
	ret = wmi_driver_register(&fevm_wmi_driver);
	if (ret) {
		pr_err("%s: Failed to register WMI driver: %d\n", DRV_NAME, ret);
		return ret;
	}

	/* Check if WMI device already exists */
	if (!fan_wmi_dev) {
		/* The device might be bound after driver registration */
		pr_info("%s: Waiting for WMI device to be probed...\n", DRV_NAME);
	}

	/* Create platform device for sysfs */
	fevm_pdev = platform_device_alloc(DRV_NAME, PLATFORM_DEVID_NONE);
	if (!fevm_pdev) {
		pr_err("%s: Failed to allocate platform device\n", DRV_NAME);
		wmi_driver_unregister(&fevm_wmi_driver);
		return -ENOMEM;
	}

	fevm_pdev->dev.groups = fevm_attr_groups;

	ret = platform_device_add(fevm_pdev);
	if (ret) {
		pr_err("%s: Failed to add platform device: %d\n", DRV_NAME, ret);
		platform_device_put(fevm_pdev);
		wmi_driver_unregister(&fevm_wmi_driver);
		return ret;
	}

	pr_info("%s: FEVM FA880 PRO Fan Control initialized\n", DRV_NAME);
	pr_info("%s: Sysfs: /sys/devices/platform/%s/fan1_duty\n", DRV_NAME, DRV_NAME);
	pr_info("%s: Sysfs: /sys/devices/platform/%s/fan2_duty\n", DRV_NAME, DRV_NAME);

	return 0;
}

static void __exit fevm_exit(void)
{
	pr_info("%s: Exiting\n", DRV_NAME);

	if (fevm_pdev) {
		platform_device_unregister(fevm_pdev);
		fevm_pdev = NULL;
	}

	wmi_driver_unregister(&fevm_wmi_driver);
	fan_wmi_dev = NULL;
}

module_init(fevm_init);
module_exit(fevm_exit);

MODULE_AUTHOR("FEVM Fan Control");
MODULE_DESCRIPTION("FEVM FA880 PRO Fan Control via ACPI-WMI");
MODULE_LICENSE("GPL");
MODULE_VERSION("1.0");
